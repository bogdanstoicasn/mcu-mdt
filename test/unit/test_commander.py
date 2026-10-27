"""
COMMANDER / SERIAL LINK TESTS FOR MCU-MDT

The poll thread, the RX thread and the main thread all write to one serial port, and the
MCU's replies arrive through one queue. These tests pin down what keeps them apart:
1. A command takes only the reply to its own request (command id, sequence, address)
2. Replies left from an earlier, timed-out command are dropped before sending
3. While a command holds the link, no other thread can send (the event poll is skipped)
"""

import threading

from pc_tool.commander import Commander
from pc_tool.common.uart_io import MCUSerialLink
from pc_tool.wire_protocol import Command, CommandId, Flag, MemType, Offset, crc16, encode
from test.common.asserts import assert_eq

_READ = Command(name="READ_MEM", id=CommandId.READ_MEM, mem=MemType.RAM, address=0x20000000, length=4)


def _ack(request: bytes, address: int | None = None) -> bytes:
    """The MCU's ACK: the request echoed with the ACK flag (and, for tests, another address)."""
    pkt = bytearray(request)
    pkt[Offset.FLAGS] |= Flag.ACK_NACK
    if address is not None:
        pkt[Offset.ADDRESS:Offset.ADDRESS + 4] = address.to_bytes(4, "little")
    pkt[Offset.CRC:Offset.CRC + 2] = crc16(pkt[Offset.CMD_ID:Offset.CRC]).to_bytes(2, "little")
    return bytes(pkt)


class _ScriptedLink:
    """A link whose MCU answers each sent packet with script(packet)."""

    def __init__(self, script, queued=()):
        self.lock, self.script, self.queue, self.sent = threading.RLock(), script, list(queued), []

    def drop_responses(self):
        self.queue.clear()

    def send_packet(self, pkt):
        self.sent.append(pkt)
        self.queue.extend(self.script(pkt))

    def get_response_packet(self, timeout=1.0):
        return self.queue.pop(0) if self.queue else None


def test_reply_to_another_request_is_not_taken():
    link = _ScriptedLink(lambda req: [_ack(req, address=0x20000004)])
    assert_eq(Commander(link).execute(_READ), False)
    assert_eq(len(link.sent), 3)                       # every retry saw only the wrong reply


def test_own_reply_is_found_behind_another_one():
    link = _ScriptedLink(lambda req: [_ack(req, address=0x20000004), _ack(req)])
    assert_eq(Commander(link).execute(_READ), True)
    assert_eq(len(link.sent), 1)


def test_reply_of_an_earlier_timed_out_command_is_dropped():
    late = _ack(encode(_READ, seq=0, multi=False, last=False))
    link = _ScriptedLink(lambda req: [], queued=[late])  # the MCU stays silent this time
    assert_eq(Commander(link).execute(_READ), False)


class _FakeSerial:
    is_open = True

    def write(self, data):
        pass

    def flush(self):
        pass


def test_no_other_thread_sends_while_a_command_holds_the_link():
    link = MCUSerialLink(port="socket://unused")
    link.ser = _FakeSerial()
    results = []
    with link.lock:                                   # what Commander does for one exchange
        worker = threading.Thread(target=lambda: results.append(link.try_send_packet(b"poll")))
        worker.start()
        worker.join()
    assert_eq(results, [False])
    assert_eq(link.try_send_packet(b"poll"), True)    # free again once the command is done

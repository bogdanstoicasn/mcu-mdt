"""
COMMAND CLIENT TESTS (pc_tool/command_client.py), through a real link and event pump on an in-process fake MCU

Coverage:
1. Packets: one per word, with seq, MULTI and LAST; data padded; PING goes out bare (length 0)
2. A command takes only the reply to its own request (command id, sequence, address)
3. A reply left from an earlier, timed-out command is dropped before sending
4. A NACK or silence means a resend; after the last attempt NoReplyError (code 4) keeps the replies so far
5. Bug 1: a corrupted reply is dropped and the packet resent, instead of crashing the tool
"""

import time

from pc_tool import command_client, event_pump, serial_link, wire_protocol
from pc_tool.command_client import NoReplyError
from pc_tool.wire_protocol import Command, CommandId, Flag, MemType, Offset
from test.common.asserts import assert_eq
from test.common.fake_mcu import FakeMcu, FakeSerialPort, crc16

_READ = Command(name="READ_MEM", id=CommandId.READ_MEM, mem=MemType.RAM, address=0x20000000, length=4)


def _client(answer=None):
    """A client on a fake MCU; *answer(mcu, request)* may replace the MCU's reply."""
    mcu = FakeMcu()
    port = FakeSerialPort(mcu, answer=(lambda request: answer(mcu, request)) if answer else None)
    link = serial_link.SerialLink("fake")
    link.open(port)
    pump = event_pump.EventPump(link, uart_idle=False, on_event=lambda event: None)
    pump.start()
    return command_client.CommandClient(link, reply_timeout=0.2), port, pump


def _reseal(packet: bytes, **fields) -> bytes:
    """*packet* with fields changed (address=, flags=, crc_ok=False) and its CRC recomputed (or broken)."""
    out = bytearray(packet)
    if "address" in fields:
        out[Offset.ADDRESS:Offset.ADDRESS + 4] = fields["address"].to_bytes(4, "little")
    if "flags" in fields:
        out[Offset.FLAGS] = fields["flags"]
    crc = crc16(bytes(out[Offset.CMD_ID:Offset.CRC])) ^ (0 if fields.get("crc_ok", True) else 0xFFFF)
    out[Offset.CRC:Offset.CRC + 2] = crc.to_bytes(2, "little")
    return bytes(out)


def _run(client, pump, command):
    try:
        return client.run(command)
    finally:
        pump.stop()


# ---------------------------------------------------------------- 1. packets

def test_one_packet_per_word_with_seq_multi_and_last():
    client, port, pump = _client()
    write = Command(name="WRITE_MEM", id=CommandId.WRITE_MEM, mem=MemType.RAM, address=0x20000000,
                    length=10, data=bytes(range(10)))
    replies = _run(client, pump, write)
    sent = [wire_protocol.decode(p) for p in port.written]
    assert_eq([(p.seq, p.address, p.length, p.data) for p in sent],
              [(0, 0x20000000, 4, bytes([0, 1, 2, 3])), (1, 0x20000004, 4, bytes([4, 5, 6, 7])),
               (2, 0x20000008, 2, bytes([8, 9, 0, 0]))])
    assert_eq([bool(p.flags & Flag.SEQ_PRESENT) for p in sent], [True, True, True])
    assert_eq([bool(p.flags & Flag.LAST_PACKET) for p in sent], [False, False, True])
    assert_eq(len(replies), 3)


def test_a_one_word_command_is_one_plain_packet():
    client, port, pump = _client()
    _run(client, pump, _READ)
    packet = wire_protocol.decode(port.written[0])
    assert_eq((len(port.written), packet.length, bool(packet.flags & Flag.SEQ_PRESENT)), (1, 4, False))


def test_ping_goes_out_bare():
    client, port, pump = _client()
    _run(client, pump, Command(name="PING", id=CommandId.PING))
    assert_eq(port.written, [wire_protocol.encode(Command(name="PING", id=CommandId.PING))])
    assert_eq(wire_protocol.decode(port.written[0]).length, 0)


# ---------------------------------------------------------------- 2.-3. matching

def test_reply_to_another_request_is_not_taken():
    client, port, pump = _client(lambda mcu, request: _reseal(mcu.handle(request), address=0x20000004))
    try:
        _run(client, pump, _READ)
    except NoReplyError as exc:
        assert_eq((str(exc), exc.code), ("Command failed after 3 attempts (seq=0). Aborting.", 4))
    else:
        raise AssertionError("a reply to another address was taken")
    assert_eq(len(port.written), 3)                   # every attempt saw only the wrong reply


def test_own_reply_is_found_behind_another_one():
    client, port, pump = _client(lambda mcu, request: _reseal(mcu.handle(request), address=0x20000004)
                                 + mcu.handle(request))
    assert_eq(len(_run(client, pump, _READ)), 1)
    assert_eq(len(port.written), 1)


def test_reply_of_an_earlier_timed_out_command_is_dropped():
    client, port, pump = _client(lambda mcu, request: b"")          # the MCU stays silent
    late = _reseal(wire_protocol.encode(_READ), flags=Flag.LENGTH_PRESENT | Flag.MEM_ID_PRESENT | Flag.ACK_NACK)
    port.inject(late)
    deadline = time.monotonic() + 2
    while client._link.replies.empty() and time.monotonic() < deadline:   # let the pump queue it first
        time.sleep(0.01)
    try:
        _run(client, pump, _READ)
    except NoReplyError:
        pass
    else:
        raise AssertionError("the late reply was taken")


# ---------------------------------------------------------------- 4. retries

def test_nack_then_ack_succeeds_on_the_second_attempt():
    nack = _reseal(bytes([0xAA, 0, Flag.ACK_NACK | Flag.STATUS_ERROR] + [0] * 14 + [0x55]))
    answers = iter([nack])
    client, port, pump = _client(lambda mcu, request: next(answers, None) or mcu.handle(request))
    assert_eq(len(_run(client, pump, _READ)), 1)
    assert_eq(len(port.written), 2)


def test_no_reply_error_keeps_the_replies_so_far():
    answered = []

    def first_packet_only(mcu, request):
        answered.append(request)
        return mcu.handle(request) if len(answered) == 1 else b""

    client, port, pump = _client(first_packet_only)
    write = Command(name="WRITE_MEM", id=CommandId.WRITE_MEM, mem=MemType.RAM, address=0x20000000,
                    length=8, data=bytes(8))
    try:
        _run(client, pump, write)
    except NoReplyError as exc:
        assert_eq((len(exc.replies), str(exc)), (1, "Command failed after 3 attempts (seq=1). Aborting."))
    else:
        raise AssertionError("no NoReplyError")


def test_ping_failure_message():
    client, _, pump = _client(lambda mcu, request: b"")
    try:
        _run(client, pump, Command(name="PING", id=CommandId.PING))
    except NoReplyError as exc:
        assert_eq(str(exc), "Ping failed after 3 attempts.")
    else:
        raise AssertionError("no NoReplyError")


# ---------------------------------------------------------------- 5. bug 1

def test_a_corrupted_reply_is_resent_not_a_crash():
    corrupt = iter([True])
    client, port, pump = _client(lambda mcu, request: _reseal(mcu.handle(request), crc_ok=not next(corrupt, False)))
    replies = _run(client, pump, _READ)
    assert_eq(len(port.written), 2)                   # the first reply failed its CRC: resent once
    assert_eq(replies[0].data, bytes([0, 1, 2, 3]))   # the fake MCU's pattern at 0x20000000

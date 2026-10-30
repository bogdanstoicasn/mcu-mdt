"""Send one Command and collect its replies.

A command longer than a word goes out as one packet per word (sequence numbers, MULTI and LAST
flags). Each packet holds the link for its whole exchange and waits for its own reply: an ACK
echoing its command id, sequence and address, or a NACK. A NACK or no reply within the timeout
means a resend, up to MAX_ATTEMPTS sends. Replies arrive already decoded and CRC-checked by the
event pump, so a corrupted reply counts as no reply and is retried.
"""

import logging
import time

from pc_tool import MdtError, serial_link, wire_protocol

log = logging.getLogger(__name__)

REPLY_TIMEOUT = 1.0     # seconds per attempt
MAX_ATTEMPTS = 3        # sends per packet before giving up


class NoReplyError(MdtError):
    """A packet got no valid reply after every attempt. `replies` holds the ones that did."""

    code = 4

    def __init__(self, message: str, replies: list[wire_protocol.Packet]) -> None:
        super().__init__(message)
        self.replies = replies


class CommandClient:
    def __init__(self, link: serial_link.SerialLink, reply_timeout: float = REPLY_TIMEOUT) -> None:
        self._link = link
        self._reply_timeout = reply_timeout

    def run(self, command: wire_protocol.Command) -> list[wire_protocol.Packet]:
        """Send *command*; return one reply per packet sent. Raise NoReplyError if one gets none."""
        replies = []
        for seq, packet in _packets(command):
            log.info("Serialized Command Packet: %s", packet.hex())
            reply = self._exchange(packet)
            if reply is None:
                message = (f"Ping failed after {MAX_ATTEMPTS} attempts." if command.id == wire_protocol.CommandId.PING
                           else f"Command failed after {MAX_ATTEMPTS} attempts (seq={seq}). Aborting.")
                raise NoReplyError(message, replies)
            log.info("Received ACK: %s", reply.raw.hex())
            if reply.is_error:
                log.error("Command execution error indicated by status flag.", extra={"code": "(3)"})
            else:
                log.info("Command packet validation successful.")
            replies.append(reply)
        return replies

    def _exchange(self, packet: bytes) -> wire_protocol.Packet | None:
        """Send *packet* until it gets its reply. Replies left from an earlier, timed-out command
        are dropped first; holding the link keeps the event poll out meanwhile."""
        sent = wire_protocol.decode(packet)
        with self._link.lock:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                self._link.drop_replies()
                self._link.send(packet)
                reply = self._await_reply(sent)
                if reply is None:
                    log.warning("No response from MCU for seq=%d (attempt %d/%d).", sent.seq, attempt, MAX_ATTEMPTS)
                elif reply.is_nack:
                    log.warning("NACK received for seq=%d (attempt %d/%d), retrying...", reply.seq, attempt,
                                MAX_ATTEMPTS)
                else:
                    return reply
        return None

    def _await_reply(self, sent: wire_protocol.Packet) -> wire_protocol.Packet | None:
        """The reply to *sent*. A NACK carries none of its fields, but it can only be ours: nothing
        else is sent while a command holds the link. Replies to anything else are dropped."""
        deadline = time.monotonic() + self._reply_timeout
        while (left := deadline - time.monotonic()) > 0:
            reply = self._link.next_reply(left)
            if reply is None:
                return None
            if reply.is_nack or (reply.is_ack and (reply.cmd_id, reply.seq, reply.address)
                                 == (sent.cmd_id, sent.seq, sent.address)):
                return reply
            log.info("Dropped a reply to another request: %s", reply.raw.hex())
        return None


def _packets(command: wire_protocol.Command) -> list[tuple[int, bytes]]:
    """(seq, packet) for every word of *command*."""
    if command.id == wire_protocol.CommandId.PING:
        return [(0, wire_protocol.encode(command))]     # bare, length 0, as the startup sync sends it
    length = command.length if command.length is not None else wire_protocol.WORD_SIZE
    packets = []
    for index, offset in enumerate(range(0, length, wire_protocol.WORD_SIZE)):
        size = min(wire_protocol.WORD_SIZE, length - offset)
        data = None
        if command.data is not None:
            data = command.data[offset:offset + size].ljust(wire_protocol.WORD_SIZE, b"\0")
        word = wire_protocol.Command(name=command.name, id=command.id, mem=command.mem,
                                     address=command.address + offset, data=data, length=size)
        seq = index % 0xFF                              # 0..254, then wraps
        packets.append((seq, wire_protocol.encode(word, seq=seq, multi=length > wire_protocol.WORD_SIZE,
                                                  last=offset + wire_protocol.WORD_SIZE >= length)))
    return packets

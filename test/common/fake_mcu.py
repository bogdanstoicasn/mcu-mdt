"""A firmware stand-in that answers MDT packets the way src/mcu_mdt.c does.

Used by the golden tests (on a TCP socket, reached as socket://localhost:<port>) to run the real
PC tool end to end without hardware. It imports nothing from pc_tool on purpose: it is the other
side of the wire, so it must not change when the tool does.

    bad frame or CRC   -> NACK (cmd 0, ACK|ERROR, seq echoed)
    valid request      -> the request echoed with ACK (ERROR when it fails)
    READ_MEM/READ_REG  -> DATA filled from a 1 MiB byte image (a known pattern)
    WRITE_MEM/WRITE_REG-> DATA stored into it; ERASE fills the 1 KiB page with 0xFF
    CMD_ID 0 (poll)    -> carries one watchpoint change, if any
"""

import socket
import sys
import threading

PACKET_SIZE, START, END = 18, 0xAA, 0x55
ACK, ERROR, EVENT = 0x04, 0x20, 0x40
PATTERN = bytes(range(256)) * 4096


def crc16(data: bytes) -> int:
    """CRC-CCITT (poly 0x1021, init 0xFFFF), as in src/mcu_mdt_protocol.c."""
    crc = 0xFFFF
    for byte in data:
        x = ((crc >> 8) ^ byte) & 0xFF
        x ^= x >> 4
        crc = ((crc << 8) ^ (x << 12) ^ (x << 5) ^ x) & 0xFFFF
    return crc


def _seal(packet: bytearray) -> bytes:
    packet[15:17] = crc16(packet[1:15]).to_bytes(2, "little")
    return bytes(packet)


class FakeMcu:
    """One target: its memory and its armed watchpoints."""

    def __init__(self) -> None:
        self.memory = bytearray(PATTERN)
        self.watch: dict[int, tuple[int, int]] = {}      # slot -> (address, last reported value)

    def _word(self, address: int) -> int:
        return int.from_bytes(bytes(self.memory[(address + i) % len(self.memory)] for i in range(4)), "little")

    def handle(self, request: bytes) -> bytes:
        """The reply to one 18-byte request."""
        if (request[0] != START or request[17] != END
                or crc16(request[1:15]) != int.from_bytes(request[15:17], "little")):
            return _seal(bytearray([START, 0, ACK | ERROR, request[3]] + [0] * 13 + [END]))

        reply, cmd, mem = bytearray(request), request[1], request[4]
        address = int.from_bytes(request[5:9], "little")
        length = int.from_bytes(request[9:11], "little")
        ok = True
        if cmd == 0x00:
            self._report_watchpoint(reply)
        elif cmd in (0x01, 0x03):                         # READ_MEM, READ_REG
            n = 4 if cmd == 0x03 else min(length, 4)
            reply[11:15] = bytes(self.memory[(address + i) % len(self.memory)] for i in range(n)).ljust(4, b"\0")
        elif cmd == 0x02 and mem == 3:                    # WRITE_MEM ERASE
            for i in range(1024):
                self.memory[((address & ~1023) + i) % len(self.memory)] = 0xFF
        elif cmd in (0x02, 0x04):                         # WRITE_MEM, WRITE_REG
            for i in range(4 if cmd == 0x04 else min(length, 4)):
                self.memory[(address + i) % len(self.memory)] = request[11 + i]
        elif cmd == 0x08:                                 # WATCHPOINT: mem = control, address = slot
            if mem == 1:
                watched = int.from_bytes(request[11:15], "little")
                self.watch[address] = (watched, self._word(watched))
            elif mem in (0, 2):
                self.watch.pop(address, None)
        elif cmd not in (0x05, 0x06, 0x07):               # PING, RESET, BREAKPOINT
            ok = False
        reply[2] |= ACK if ok else ACK | ERROR
        return _seal(reply)

    def _report_watchpoint(self, reply: bytearray) -> None:
        for slot, (address, last) in self.watch.items():
            now = self._word(address)
            if now != last:
                self.watch[slot] = (address, now)
                reply[2] |= EVENT
                reply[3], reply[4] = slot, 4                  # seq = slot, mem = WATCHPOINT_HIT
                reply[5:9] = last.to_bytes(4, "little")
                reply[9:11] = (4).to_bytes(2, "little")
                reply[11:15] = now.to_bytes(4, "little")
                return


def serve(port: int = 0) -> tuple[socket.socket, int]:
    """Listen on localhost in a daemon thread; every connection gets a fresh FakeMcu.
    Returns the listening socket (close it to stop) and the port."""
    server = socket.create_server(("127.0.0.1", port))
    threading.Thread(target=_accept_forever, args=(server,), daemon=True).start()
    return server, server.getsockname()[1]


def _accept_forever(server: socket.socket) -> None:
    while True:
        try:
            conn, _ = server.accept()
        except OSError:                                   # the server socket was closed
            return
        threading.Thread(target=_talk, args=(conn,), daemon=True).start()


def _talk(conn: socket.socket) -> None:
    mcu, pending = FakeMcu(), b""
    with conn:
        while True:
            try:
                chunk = conn.recv(256)
            except OSError:
                return
            if not chunk:
                return
            pending += chunk
            while (start := pending.find(bytes([START]))) >= 0 and len(pending) - start >= PACKET_SIZE:
                conn.sendall(mcu.handle(pending[start:start + PACKET_SIZE]))
                pending = pending[start + PACKET_SIZE:]
            if START not in pending:
                pending = b""


if __name__ == "__main__":
    _, bound = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print(f"fake MCU on socket://localhost:{bound}")
    threading.Event().wait()

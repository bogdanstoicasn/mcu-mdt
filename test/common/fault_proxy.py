"""A TCP proxy between the PC tool and an emulated MCU that can damage the MCU's answers.

    proxy = FaultProxy(upstream_port)          # listens on proxy.port
    proxy.fault = corrupt_nth(2)               # a function: (packet bytes) -> bytes to forward
    proxy.unplug()                             # drop the connection, like pulling the cable

Faults work on whole 18-byte packets from the MCU (framed on the 0xAA start byte); bytes
from the PC pass through untouched.
"""

import contextlib
import socket
import threading
import time

PACKET = 18


class FaultProxy:
    def __init__(self, upstream_port: int) -> None:
        self.upstream_port = upstream_port
        self.fault = lambda packet: packet
        self.split_delay = 0.0                 # > 0: forward each byte alone with this gap
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.from_mcu: list[bytes] = []        # every packet the MCU sent, before any fault
        self._conns: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def unplug(self) -> None:
        _close(*self._conns)
        self._conns.clear()

    def close(self) -> None:
        self.unplug()
        self.server.close()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            mcu = socket.create_connection(("127.0.0.1", self.upstream_port))
            for s in (client, mcu):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._conns += [client, mcu]
            threading.Thread(target=self._pc_to_mcu, args=(client, mcu), daemon=True).start()
            threading.Thread(target=self._mcu_to_pc, args=(mcu, client), daemon=True).start()

    def _pc_to_mcu(self, client, mcu) -> None:
        try:
            while data := client.recv(256):
                mcu.sendall(data)
        except OSError:
            pass
        _close(client, mcu)

    def _mcu_to_pc(self, mcu, client) -> None:
        pending = b""
        try:
            while data := mcu.recv(256):
                pending += data
                while (start := pending.find(b"\xAA")) >= 0 and len(pending) - start >= PACKET:
                    if start:
                        self._send(client, pending[:start])
                    packet, pending = pending[start:start + PACKET], pending[start + PACKET:]
                    self.from_mcu.append(packet)
                    self._send(client, self.fault(packet))
                if b"\xAA" not in pending:
                    self._send(client, pending)
                    pending = b""
        except OSError:
            pass
        _close(client, mcu)

    def _send(self, client, data: bytes) -> None:
        if not data:
            return
        if self.split_delay:
            for i in range(len(data)):
                client.sendall(data[i:i + 1])
                time.sleep(self.split_delay)
        else:
            client.sendall(data)


def _close(*sockets) -> None:
    """Shut down first: a plain close() from another thread leaves a blocked recv() holding the socket open."""
    for s in sockets:
        with contextlib.suppress(OSError):
            s.shutdown(socket.SHUT_RDWR)
        s.close()


def is_reply(packet: bytes) -> bool:
    """A reply to a command (not a poll answer or an event)."""
    return packet[1] != 0


def nth_reply(n: int, change):
    """Apply *change* to the n-th command reply (1-based) only."""
    seen = [0]

    def fault(packet):
        if is_reply(packet):
            seen[0] += 1
            if seen[0] == n:
                return change(packet)
        return packet
    return fault


def flip_crc(packet: bytes) -> bytes:
    return packet[:15] + bytes([packet[15] ^ 0xFF]) + packet[16:]


def flip_data(packet: bytes) -> bytes:
    return packet[:11] + bytes([packet[11] ^ 0x5A]) + packet[12:]


def drop(packet: bytes) -> bytes:
    return b""


def delayed(seconds: float):
    def change(packet):
        time.sleep(seconds)
        return packet
    return change


def with_noise(packet: bytes) -> bytes:
    return b"\x00\x13\x55\xAA\x01" + packet                 # junk, including a false start byte


def doubled(packet: bytes) -> bytes:
    return packet + packet

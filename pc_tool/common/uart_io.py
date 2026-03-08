import serial
import time
import queue
from  common.enums import MDT_PACKET_SIZE, FenceType
from logger import MDTLogger

class MCUSerialLink:
    def __init__(
        self,
        port: str,
        baudrate: int = 19200,
        timeout: float = 1.0,
        reset_delay: float = 2.0,
        startup_ping: bytes | None = None
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reset_delay = reset_delay
        self.startup_ping = startup_ping
        self.running = True
        self.response_queue = queue.Queue()
        self.event_queue = queue.Queue()
        self._rx_buf = bytearray()
        self.packet_size = MDT_PACKET_SIZE
        self.ser = None
    
    def open(self):
        if self.ser is not None and self.ser.is_open:
            return
        
        self.ser = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )

        if self.reset_delay > 0:
            time.sleep(self.reset_delay)
        
        if self.startup_ping:
            self._synch_with_mcu()
    
    def close(self):
        self.running = False
        if self.ser:
            try:
                # flush input/output to avoid blocking
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception:
                pass
            self.ser.close()
            self.ser = None
        
    def _synch_with_mcu(self):
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        self.ser.write(self.startup_ping)
        self.ser.flush()

        echoed = bytearray()
        start = time.time()
        while len(echoed) < len(self.startup_ping):
            if self.ser.in_waiting > 0:
                echoed += self.ser.read(self.ser.in_waiting)

            if time.time() - start > 5.0:
                break
        if len(echoed) != len(self.startup_ping):
            MDTLogger.warning(f"Startup ping echo mismatch: expected {len(self.startup_ping)}, got {len(echoed)}")
    
    def send_packet(self, byte_packet: bytes):
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("Serial port is not open.")
        
        self.ser.write(byte_packet)
        self.ser.flush()
    
    def read_packet(self, timeout=0.1):
        """
        Reads one full MDT packet from UART.
        Resynchronizes on start byte if necessary.
        """
        if self.ser is None or not self.ser.is_open:
            return None

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.ser.in_waiting:
                self._rx_buf += self.ser.read(self.ser.in_waiting)

            # Search for start byte
            start_idx = self._rx_buf.find(FenceType.START_BYTE.to_bytes(1, 'little'))
            if start_idx == -1:
                # No start byte, discard buffer
                self._rx_buf.clear()
                continue

            # Remove any preceding junk bytes
            if start_idx > 0:
                self._rx_buf = self._rx_buf[start_idx:]

            if len(self._rx_buf) >= self.packet_size:
                pkt = self._rx_buf[:self.packet_size]
                self._rx_buf = self._rx_buf[self.packet_size:]
                
                # Optional: validate CRC here
                # if not validate_packet(pkt):
                #     continue  # discard and resync

                return bytes(pkt)

        return None
    
    def get_response_packet(self, timeout=0.1):
        try:
            return self.response_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_event_packet(self, timeout=0.1):
        try:
            return self.event_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def push_back_packet(self, pkt: bytes):
        self.response_queue.put(pkt)
    
    def push_back_event_packet(self, pkt: bytes):
        self.event_queue.put(pkt)

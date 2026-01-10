import serial
import time

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
            print(f"Warning: Startup ping echo mismatch: expected {len(self.startup_ping)}, got {len(echoed)}")
    
    def send_packet(self, byte_packet: bytes):
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("Serial port is not open.")
        
        self.ser.write(byte_packet)
        self.ser.flush()

        echoed = bytearray()
        start = time.time()
        while len(echoed) < len(byte_packet):
            if self.ser.in_waiting > 0:
                echoed += self.ser.read(self.ser.in_waiting)

            if time.time() - start > 5.0:
                break

        return echoed

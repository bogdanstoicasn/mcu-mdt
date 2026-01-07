import serial
import time

def send_packet_to_mcu(byte_packet: bytes, port: str, baudrate: int = 19200):
    """
    Sends a packet to the MCU and reads back all echoed bytes.
    Handles Arduino-style USB reset on port open.
    
    Returns the echoed bytes (bytearray).
    """
    try:
        with serial.Serial(
            port,
            baudrate,
            timeout=2.0,      # wait for bytes if they arrive slowly
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        ) as ser:

            # Delay for Arduino/ATmega328p auto-reset
            time.sleep(2.0)

            # Send packet
            ser.write(byte_packet)
            ser.flush()
            print(f"Sent {len(byte_packet)} bytes to MCU on {port}")

            # Read echoed bytes in a loop
            echoed = bytearray()
            start = time.time()
            while len(echoed) < len(byte_packet):
                if ser.in_waiting > 0:
                    echoed += ser.read(ser.in_waiting)

                # Safety timeout
                if time.time() - start > 5.0:  # 5 sec max
                    break

            print(f"Received {len(echoed)} bytes")
            print("Echoed bytes:", echoed.hex())

            if len(echoed) != len(byte_packet):
                print(f"Mismatch: expected {len(byte_packet)}, got {len(echoed)}")

            return echoed

    except Exception as e:
        print(f"Error sending packet: {e}")
        return None
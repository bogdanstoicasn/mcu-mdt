"""
CRC16 TESTS (CRC-CCITT, 0x1021)


Validates the correctness of the protocol CRC implementation
against a trusted reference (binascii.crc_hqx).

Coverage:
1. Known test vectors (e.g., "123456789")
2. Empty input
3. Randomly generated data of varying lengths (0 to 256 bytes)
4. Stress test with 1000 random inputs

Goal:
Ensure that the CRC16 implementation in the protocol matches the reference impleemntation.
"""

import random
import binascii
from test.common.asserts import assert_eq
from pc_tool.common.protocol import calculate_crc16

def reference_crc16(data: bytes) -> int:
    # CRC-CCITT (0x1021) with initial value 0xFFFF
    return binascii.crc_hqx(data, 0xFFFF)


def test_crc_known_vectors():
    """Test CRC16 against known test vectors."""
    from pc_tool.common.protocol import calculate_crc16

    # Standard test vector
    assert_eq(calculate_crc16(b"123456789"), 0x29B1)

    # Empty
    assert_eq(calculate_crc16(b""), 0xFFFF)

def test_crc_random():
    """Test CRC16 against random data of varying lengths."""
    from pc_tool.common.protocol import calculate_crc16

    for length in [0, 1, 2, 4, 8, 16, 32, 64, 128, 256]:
        data = bytes(random.getrandbits(8) for _ in range(length))

        expected = reference_crc16(data)
        actual = calculate_crc16(data)
        assert_eq(actual, expected, data=data, length=length)

def test_crc_random_stress():
    """Stress test CRC16 with 1000 random inputs."""
    from pc_tool.common.protocol import calculate_crc16

    for _ in range(1000):
        length = random.randint(0, 256)
        data = bytes(random.getrandbits(8) for _ in range(length))

        expected = reference_crc16(data)
        actual = calculate_crc16(data)

        assert_eq(actual, expected, data=data, length=length)

def test_crc_all_zeros():
    """CRC of all zeros should be consistent and not zero (unless the polynomial causes that)."""
    assert_eq(calculate_crc16(b'\x00' * 16), calculate_crc16(b'\x00' * 16))

def test_crc_single_byte_matches_reference():
    """Test CRC16 of single-byte inputs against a known reference implementation (binascii.crc_hqx)."""
    import binascii
    for b in [0x00, 0x01, 0xFF, 0xAA, 0x55]:
        data = bytes([b])
        ref = binascii.crc_hqx(data, 0xFFFF)
        assert_eq(calculate_crc16(data), ref)

def test_crc_is_deterministic():
    data = bytes(range(16))
    assert_eq(calculate_crc16(data), calculate_crc16(data))

def test_crc_different_data_different_result():
    a = calculate_crc16(b'\xAA\xBB\xCC\xDD')
    b = calculate_crc16(b'\xAA\xBB\xCC\xDE')   # last byte differs by 1
    assert_eq(a == b, False)
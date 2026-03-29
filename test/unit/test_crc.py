import pytest
import random
import binascii


def reference_crc16(data: bytes) -> int:
    # CRC-CCITT (0x1021) with initial value 0xFFFF
    return binascii.crc_hqx(data, 0xFFFF)


def test_crc_known_vectors():
    from pc_tool.common.protocol import calculate_crc16

    # Standard test vector
    assert calculate_crc16(b"123456789") == 0x29B1

    # Empty
    assert calculate_crc16(b"") == 0xFFFF


@pytest.mark.parametrize("length", [0, 1, 2, 4, 8, 16, 32, 64, 128])
def test_crc_random(length):
    from pc_tool.common.protocol import calculate_crc16

    data = bytes(random.getrandbits(8) for _ in range(length))

    expected = reference_crc16(data)
    actual = calculate_crc16(data)

    assert actual == expected, (
        f"\nData: {data.hex()}\n"
        f"Expected: 0x{expected:04X}, Got: 0x{actual:04X}"
    )

def test_crc_random_stress():
    from pc_tool.common.protocol import calculate_crc16

    for _ in range(1000):
        length = random.randint(0, 256)
        data = bytes(random.getrandbits(8) for _ in range(length))

        expected = binascii.crc_hqx(data, 0xFFFF)
        actual = calculate_crc16(data)

        assert actual == expected
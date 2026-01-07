#include "mcu_mdt.h"
#include "mcu_mdt_private.h"
#include "mcu_mdt_hal.h"

void mcu_mdt_init(void)
{
    // Initialization code for MCU MDT
    hal_uart_init();
}

static mdt_packet_t rx_packet = { 0 };

static uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len)
{
    uint16_t crc_rx;
    uint16_t crc_calc = 0;
    uint16_t length_field;

    if (!buf)
    {
        return 0;
    }

    if (len != MDT_PACKET_SIZE)
    {
        return 0;
    }

    if (buf[0] != START_BYTE || buf[len - 1] != END_BYTE)
    {
        return 0;
    }

    // Calculate CRC
    length_field = (uint16_t)buf[MDT_OFFSET_LENGTH] | ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);

    if (length_field > MDT_DATA_MAX_SIZE)
    {
        return 0;
    }

    crc_rx = (uint16_t)buf[MDT_OFFSET_CRC] | ((uint16_t)buf[MDT_OFFSET_CRC + 1] << 8);

    (void)crc_calc;
    (void)crc_rx;

    //TODO: Implement actual CRC calculation

    return 1; // For now, always return valid
    
}

void mcu_mdt_poll(void)
{
    uint8_t byte;

    while (hal_uart_rx(&byte))
    {
        // Echo back every byte immediately
        hal_uart_tx(byte);
    }
}


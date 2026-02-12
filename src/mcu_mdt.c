#include "mcu_mdt.h"
#include "mcu_mdt_private.h"
#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"

void mcu_mdt_init(void)
{
    // Initialization code for MCU MDT
    hal_uart_init();
}

static mdt_buffer_t rx_packet = { 0 };

static uint16_t mdt_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    uint8_t x;

    while(len--)
    {
        x = crc >> 8 ^ *data++;
        x ^= x >> 4;
        crc = (crc << 8) ^ ((uint16_t)(x << 12)) ^ ((uint16_t)(x <<5)) ^ ((uint16_t)x);
    }

    return crc;
}

static uint8_t mdt_memset(uint8_t *buf, uint8_t value, uint16_t len)
{
    if (!buf)
    {
        return 0;
    }

    for (uint16_t i = 0; i < len; i++)
    {
        buf[i] = value;
    }

    return 1;
}

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

    if (buf[0] != MDT_START_BYTE || buf[len - 1] != MDT_END_BYTE)
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

    crc_calc = mdt_crc16(&buf[MDT_OFFSET_CMD_ID], MDT_PACKET_SIZE - 5);

    return (crc_rx == crc_calc);
}

void mcu_mdt_poll(void)
{
    uint8_t byte;

    while (hal_uart_rx(&byte))
    {
        /* Wait for START byte */
        if (!rx_packet.started)
        {
            if (byte != MDT_START_BYTE)
                continue;

            rx_packet.started = 1;
            rx_packet.idx = 0;
            rx_packet.buf[rx_packet.idx++] = byte;
            continue;
        }

        /* Prevent overflow */
        if (rx_packet.idx >= MDT_PACKET_MAX_SIZE)
        {
            rx_packet.started = 0;
            rx_packet.idx = 0;
            continue;
        }

        /* Store byte */
        rx_packet.buf[rx_packet.idx++] = byte;

        /* Full packet received */
        if (rx_packet.idx == MDT_PACKET_SIZE)
        {
            uint8_t valid = 1;

            /* END byte check */
            if (rx_packet.buf[MDT_OFFSET_END] != MDT_END_BYTE)
            {
                valid = 0;
            }

            /* CRC check */
            if (valid)
            {
                uint16_t rx_crc =
                    rx_packet.buf[MDT_OFFSET_CRC] |
                    ((uint16_t)rx_packet.buf[MDT_OFFSET_CRC + 1] << 8);

                uint16_t calc_crc =
                    mdt_crc16(
                        &rx_packet.buf[MDT_OFFSET_CMD_ID],
                        MDT_PACKET_SIZE
                        - MDT_OFFSET_CMD_ID
                        - 2   /* CRC */
                        - 1   /* END */
                    );

                if (rx_crc != calc_crc)
                    valid = 0;
            }

            /* ACK / NACK */
            if (valid)
            {
                rx_packet.buf[MDT_OFFSET_FLAGS] |= MDT_FLAG_ACK_NACK;
                /* TODO: command dispatch */
            }
            else
            {
                rx_packet.buf[MDT_OFFSET_FLAGS] &= ~MDT_FLAG_ACK_NACK;
            }

            /* Send reply */
            for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
            {
                hal_uart_tx(rx_packet.buf[i]);
            }

            /* Reset RX state */
            rx_packet.started = 0;
            rx_packet.idx = 0;
        }
    }
}

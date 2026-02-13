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

void mcu_mdt_poll(void)
{
    uint8_t byte;

    while (hal_uart_rx(&byte))
    {
        /* ----------------------------- */
        /* Wait for START byte           */
        /* ----------------------------- */
        if (!rx_packet.started)
        {
            if (byte != MDT_START_BYTE)
                continue;

            rx_packet.started = 1;
            rx_packet.idx = 0;
            rx_packet.buf[rx_packet.idx++] = byte;
            continue;
        }

        /* ---------------------------------- */
        /* Resync if new START appears mid-packet */
        /* ---------------------------------- */
        // if (byte == MDT_START_BYTE)
        // {
        //     rx_packet.idx = 0;
        //     rx_packet.buf[rx_packet.idx++] = byte;
        //     continue;
        // }

        /* ----------------------------- */
        /* Prevent buffer overflow       */
        /* ----------------------------- */
        if (rx_packet.idx >= MDT_PACKET_MAX_SIZE)
        {
            rx_packet.started = 0;
            rx_packet.idx = 0;
            continue;
        }

        /* ----------------------------- */
        /* Store incoming byte           */
        /* ----------------------------- */
        rx_packet.buf[rx_packet.idx++] = byte;

        /* ----------------------------- */
        /* Full packet received          */
        /* ----------------------------- */
        if (rx_packet.idx == MDT_PACKET_SIZE)
        {
            uint8_t valid;

            /* Validate packet */
            valid = mdt_packet_validate(
                        rx_packet.buf,
                        MDT_PACKET_SIZE
                    );

            if (valid)
            {
                /* Set ACK flag */
                rx_packet.buf[MDT_OFFSET_FLAGS] |= MDT_FLAG_ACK_NACK;

                uint8_t status = mdt_dispatch(rx_packet.buf);

                /* It comes set on 0 so no need to clear again */
                if(!status)
                {
                    /* Set error flag */
                    rx_packet.buf[MDT_OFFSET_FLAGS] |= MDT_FLAG_STATUS_ERROR;
                }

                /* Recalculate CRC */
                    uint16_t crc = mdt_crc16(
                    &rx_packet.buf[MDT_OFFSET_CMD_ID],
                    MDT_PACKET_SIZE
                        - 1 /* START */
                        - 2 /* CRC */
                        - 1 /* END */
                );

                rx_packet.buf[MDT_OFFSET_CRC]     = (uint8_t)(crc);
                rx_packet.buf[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

            }

            for (uint16_t i = 0; i < MDT_PACKET_SIZE; i++)
            {
                hal_uart_tx(rx_packet.buf[i]);
            }

            /* Reset buffer for next packet */
            rx_packet.started = 0;
            rx_packet.idx = 0;

        }
    }
}


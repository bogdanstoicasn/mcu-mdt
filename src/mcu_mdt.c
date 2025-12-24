#include "mcu_mdt.h"
#include "mcu_mdt_private.h"
#include "mcu_mdt_hal.h"

void mcu_mdt_init(void)
{
    // Initialization code for MCU MDT
    hal_uart_init();
}

static mdt_packet_t rx_packet = { 0 };

void mcu_mdt_poll(void)
{
    uint8_t byte;
    while (hal_uart_rx(&byte))
    {
        if (!rx_packet.started)
        {
            if (byte == START_BYTE) 
            {
                rx_packet.started = 1;
                rx_packet.idx = 0;
                rx_packet.buf[rx_packet.idx++] = byte;
            }
            continue; // discard until START_BYTE
        }

        rx_packet.buf[rx_packet.idx++] = byte;

        if (byte == END_BYTE || rx_packet.idx >= MDT_PACKET_MAX_SIZE)
        {
            // packet complete
            // TODO
            // handle_packet(&rx_packet);

            // reset packet
            rx_packet.idx = 0;
            rx_packet.started = 0;
        }
    }
}

#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_event.h"

__attribute__((always_inline)) inline void mdt_send_event(mdt_event_type_t event)
{
    if (!hal_uart_tx_ready())
        return; // UART busy, skip event

    mdt_packet_t pkt = {0};
    pkt.cmd_id = 0;                // Event packet
    pkt.flags |= MDT_FLAG_EVENT;   // Event flag
    pkt.seq = 0;
    pkt.mem_id = 0;
    pkt.address = 0;
    pkt.length = 1;                // 1 byte of event type
    pkt.data[0] = event;

    // Compute CRC over everything except the CRC itself
    pkt.crc = mdt_crc16((uint8_t *)&pkt, sizeof(pkt) - sizeof(pkt.crc));

    hal_uart_tx(MDT_START_BYTE);
    for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
        hal_uart_tx(((uint8_t *)&pkt)[i]);
    hal_uart_tx(MDT_END_BYTE);
}
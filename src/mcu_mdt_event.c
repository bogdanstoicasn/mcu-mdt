#include "mcu_mdt_event.h"
#include "ring_buffer.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_protocol.h"

static ring_buffer_t event_queue = {
    .buf = {0},
    .head = 0,
    .tail = 0
};

uint8_t mdt_event_push(mdt_event_type_t event)
{
    return rb_push(&event_queue, (uint8_t)event);
}

uint8_t mdt_event_pending(void)
{
    return !rb_is_empty(&event_queue);
}

void mdt_event_send_pending()
{
    uint8_t event;
    mdt_packet_t pkt;

    while (rb_pop(&event_queue, &event))
    {
        pkt.cmd_id = 0; // Example event type, can be extended
        pkt.flags |= MDT_FLAG_EVENT; // Set event flag
        pkt.seq = 0; // Not used for events
        pkt.mem_id = 0; // Not used for events
        pkt.address = 0; // Not used for events
        pkt.length = 1; // Event data length
        pkt.data[0] = event; // Event type in data

        pkt.crc = mdt_crc16((uint8_t *)&pkt, sizeof(mdt_packet_t) - sizeof(pkt.crc));

        hal_uart_tx(MDT_START_BYTE);
        for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
        {
            // Here you would send the packet byte by byte to the host
            hal_uart_tx(((uint8_t *)&pkt)[i]);
        }
        hal_uart_tx(MDT_END_BYTE);

    }
}


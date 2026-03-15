#include "mcu_mdt.h"
#include "mcu_mdt_private.h"
#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"

static mdt_buffer_t rx_packet = {
    .fence_pre = MDT_FENCE_PATTERN,
    .idx = 0,
    .started = 0,
    .buf = {0},
    .fence_post = MDT_FENCE_PATTERN
};

static inline void mdt_memset(void *buf, uint8_t value, uint32_t len)
{
    uint8_t *p = (uint8_t *)buf;

    while (len--)
    {
        *p++ = value;
    }
}

static volatile mdt_event_t pending_event = { .raw = 0 };

/* --- Event handling functions --- */

static inline void mdt_event_set(mdt_event_type_t type, uint32_t data)
{
    if (pending_event.raw)
        return; // event already pending
    pending_event.type = type;
    pending_event.data = data;
}

static inline void mdt_event_clear(void)
{
    pending_event.raw = 0;
}

static inline uint8_t mdt_event_pending(void)
{
    return pending_event.raw != 0;
}

void mdt_event_send(void)
{
    if (!mdt_event_pending())
        return; // No event to send

    if (!hal_uart_tx_ready())
        return; // UART busy, skip event
    
    mdt_packet_t pkt;
    mdt_memset((uint8_t *)&pkt, 0, sizeof(pkt));
    pkt.flags |= MDT_FLAG_EVENT;   // Event flag
    pkt.length = 4;                // 4 bytes of event data
    pkt.data[0] = (uint8_t)(pending_event.raw & 0xFF);
    pkt.data[1] = (uint8_t)((pending_event.raw >> 8) & 0xFF);
    pkt.data[2] = (uint8_t)((pending_event.raw >> 16) & 0xFF);
    pkt.data[3] = (uint8_t)((pending_event.raw >> 24) & 0xFF);

    // Compute CRC over everything except the CRC itself
    pkt.crc = mdt_crc16((uint8_t *)&pkt, sizeof(pkt) - sizeof(pkt.crc));

    hal_uart_tx(MDT_START_BYTE);
    for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
        hal_uart_tx(((uint8_t *)&pkt)[i]);
    hal_uart_tx(MDT_END_BYTE);

    mdt_event_clear();
}

void mdt_event_wrapper(mdt_event_type_t type, uint32_t data)
{
    mdt_event_set(type, data);
    mdt_event_send();
}

/* --- End of event handling functions --- */


/* --- Buffer management functions --- */

static inline uint8_t mdt_buffer_check(const mdt_buffer_t *buffer)
{
    return (buffer->fence_pre == MDT_FENCE_PATTERN) && (buffer->fence_post == MDT_FENCE_PATTERN);
}

static void mdt_buffer_reset(mdt_buffer_t *buffer)
{
    if (!buffer)
        return;

    buffer->idx = 0;
    buffer->started = 0;
    mdt_memset(buffer->buf, 0, MDT_PACKET_SIZE);

    buffer->fence_pre = MDT_FENCE_PATTERN;
    buffer->fence_post = MDT_FENCE_PATTERN;
}

/* --- End of buffer management functions --- */

/* Handle a full packet. Returns 1 if success, 0 if fence/critical error */
static uint8_t mdt_handle_packet(mdt_buffer_t *buf)
{
    /* --- Validate packet --- */
    uint8_t *pkt = buf->buf;
    if (!mdt_packet_validate(pkt, MDT_PACKET_SIZE))
    {
        mdt_event_wrapper(MDT_EVENT_FAILED_PACKET, ((uintptr_t)buf) & 0xFFFFFF); // Send event with buffer address for debugging
        mdt_buffer_reset(buf);
        return 0;
    }

    /* --- Dispatch command --- */
    uint8_t status = mdt_dispatch(pkt);

    /* --- Set flags --- */
    pkt[MDT_OFFSET_FLAGS] |= MDT_FLAG_ACK_NACK;
    if (!status)
        pkt[MDT_OFFSET_FLAGS] |= MDT_FLAG_STATUS_ERROR;

    /* --- Recalculate CRC --- */
    uint16_t crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE - 1 - 2 - 1
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    /* --- Send response --- */
    uint8_t *p   = pkt;
    uint8_t *end = pkt + MDT_PACKET_SIZE;
    while (p < end)
        hal_uart_tx(*p++);

    /* --- Reset buffer for next packet --- */
    mdt_buffer_reset(buf);

    return 1;
}

void mcu_mdt_init(void)
{
    // Initialization code for MCU MDT
    hal_uart_init();
}

/* --- Poll function --- */
void mcu_mdt_poll(void)
{
    uint8_t byte;

    /* --- Check for pending events --- */
    if (mdt_event_pending())
    {
        mdt_event_send();
    }

    /* --- Fence check at entry (optional) --- */
    if (!mdt_buffer_check(&rx_packet))
    {
        mdt_buffer_reset(&rx_packet);
        // send the 24 bits of lower address as event data for easier debugging
        mdt_event_wrapper(MDT_EVENT_BUFFER_OVERFLOW, ((uintptr_t)&rx_packet) & 0xFFFFFF);
        return;
    }

    while (hal_uart_rx(&byte))
    {
        /* Wait for START byte */
        if (!rx_packet.started)
        {
            if (byte != MDT_START_BYTE) continue;
            rx_packet.started = 1;
            rx_packet.idx = 0;
            rx_packet.buf[rx_packet.idx++] = byte;
            continue;
        }

        /* Prevent buffer overflow */
        if (rx_packet.idx >= MDT_PACKET_SIZE)
        {
            mdt_buffer_reset(&rx_packet);
            mdt_event_wrapper(MDT_EVENT_BUFFER_OVERFLOW, ((uintptr_t)&rx_packet) & 0xFFFFFF); // Send event with buffer address for debugging
            continue;
        }

        /* Store byte */
        rx_packet.buf[rx_packet.idx++] = byte;

        /* Full packet received */
        if (rx_packet.idx == MDT_PACKET_SIZE)
        {
            /* Handle the packet */
            if (!mdt_handle_packet(&rx_packet))
            {
                /* Fence/validation failed → break current loop iteration */
                break;
            }
        }
    }
}

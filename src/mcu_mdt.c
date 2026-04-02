#include "mcu_mdt.h"
#include "mcu_mdt_private.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_watchpoint.h"

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

static volatile mdt_event_t pending_event = { 0 };

/* Event handling functions */

static inline void mdt_event_set(mdt_event_type_t type, uint32_t data)
{
    if (pending_event.type != INTERNAL_MDT_EVENT_TYPE_NONE)
        return; /* event already pending */
    pending_event.data = data;
    pending_event.type = (uint8_t)type;
}

static inline void mdt_event_clear(void)
{
    pending_event.data = 0;
    pending_event.type = INTERNAL_MDT_EVENT_TYPE_NONE;
}

static inline uint8_t mdt_event_pending(void)
{
    return pending_event.type != INTERNAL_MDT_EVENT_TYPE_NONE;
}

void mdt_event_send(void)
{
    if (!mdt_event_pending())
        return;

    if (!hal_uart_tx_ready())
        return;

    uint8_t pkt[MDT_PACKET_SIZE] = {0};

    pkt[MDT_OFFSET_START] = MDT_START_BYTE;
    pkt[MDT_OFFSET_FLAGS] = INTERNAL_MDT_FLAG_EVENT;

    /* Event type in address field */
    pkt[MDT_OFFSET_ADDRESS] = (uint8_t)(pending_event.type);

    /* Full 32-bit event data in data field (little-endian) */
    pkt[MDT_OFFSET_DATA]     = (uint8_t)(pending_event.data & 0xFF);
    pkt[MDT_OFFSET_DATA + 1] = (uint8_t)((pending_event.data >> 8)  & 0xFF);
    pkt[MDT_OFFSET_DATA + 2] = (uint8_t)((pending_event.data >> 16) & 0xFF);
    pkt[MDT_OFFSET_DATA + 3] = (uint8_t)((pending_event.data >> 24) & 0xFF);

    pkt[MDT_OFFSET_END] = MDT_END_BYTE;

    uint16_t crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE - 1 - 2 - 1  /* exclude START, CRC, END */
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
        hal_uart_tx(pkt[i]);

    mdt_event_clear();
}

void mdt_event_wrapper(mdt_event_type_t type, uint32_t data)
{
    mdt_event_set(type, data);
    mdt_event_send();
}

/* End of event handling functions */


/* Buffer management functions */

static inline uint8_t mdt_buffer_check(const mdt_buffer_t *buffer)
{
    return (buffer->fence_pre == MDT_FENCE_PATTERN) && (buffer->fence_post == MDT_FENCE_PATTERN);
}

static void mdt_buffer_reset(mdt_buffer_t *buffer)
{
    buffer->idx     = 0;
    buffer->started = 0;
    mdt_memset(buffer->buf, 0, MDT_PACKET_SIZE);
    buffer->fence_pre  = MDT_FENCE_PATTERN;
    buffer->fence_post = MDT_FENCE_PATTERN;
}

/* End of buffer management functions */

static void mdt_send_nack(const uint8_t *buf)
{
    uint8_t pkt[MDT_PACKET_SIZE] = {0};

    pkt[MDT_OFFSET_START] = MDT_START_BYTE;
    pkt[MDT_OFFSET_FLAGS] = INTERNAL_MDT_FLAG_ACK_NACK | INTERNAL_MDT_FLAG_STATUS_ERROR;
    pkt[MDT_OFFSET_SEQ]   = buf[MDT_OFFSET_SEQ];
    pkt[MDT_OFFSET_END]   = MDT_END_BYTE;

    uint16_t crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE - 1 - 2 - 1  /* exclude START, CRC, END */
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    for (uint8_t i = 0; i < MDT_PACKET_SIZE; i++)
        hal_uart_tx(pkt[i]);
}

/* Handle a full packet. Returns 1 if success, 0 if fence/critical error */
static uint8_t mdt_handle_packet(mdt_buffer_t *buf)
{
    /* Validate packet */
    uint8_t *pkt = buf->buf;
    if (!mdt_packet_validate(pkt, MDT_PACKET_SIZE))
    {
        mdt_send_nack(pkt); /* Send nack so PC knows to retransmit */
        mdt_event_wrapper(INTERNAL_MDT_EVENT_FAILED_PACKET, ((uintptr_t)buf) & 0xFFFFFF); /* Send event with buffer address for debugging */
        mdt_buffer_reset(buf);
        return 0;
    }

    /* Dispatch command */
    uint8_t status = mdt_dispatch(pkt);

    /* Set flags */
    pkt[MDT_OFFSET_FLAGS] |= INTERNAL_MDT_FLAG_ACK_NACK;
    if (!status)
        pkt[MDT_OFFSET_FLAGS] |= INTERNAL_MDT_FLAG_STATUS_ERROR;

    /* Recalculate CRC */
    uint16_t crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE - 1 - 2 - 1
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    /* Send response */
    uint8_t *p   = pkt;
    uint8_t *end = pkt + MDT_PACKET_SIZE;
    while (p < end)
        hal_uart_tx(*p++);

    /* Reset buffer for next packet */
    mdt_buffer_reset(buf);

    return 1;
}

void mcu_mdt_init(void)
{
    /* Initialization code for MCU MDT */
    hal_uart_init();
}

/* Poll function */
void mcu_mdt_poll(void)
{
    uint8_t byte;

    /* Check for pending events */
    if (mdt_event_pending())
    {
        mdt_event_send();
    }

    /* Fence check at entry */
    if (!mdt_buffer_check(&rx_packet))
    {
        mdt_buffer_reset(&rx_packet);
        mdt_event_wrapper(INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, ((uintptr_t)&rx_packet) & 0xFFFFFFFF);
        return;
    }

    mdt_watchpoint_poll();

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
            mdt_event_wrapper(INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, ((uintptr_t)&rx_packet) & 0xFFFFFFFF);
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
                /* Fence/validation failed, break current loop iteration */
                break;
            }
        }
    }
}

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

static mdt_event_t pending_event = { 0 };

/* Event handling functions */

void mdt_event_set(
    uint8_t seq,
    uint8_t mem_id,
    uint32_t address,
    uint16_t length,
    uint32_t data)
{
    if (pending_event.pending)
        return;

    pending_event.seq     = seq;
    pending_event.mem_id  = mem_id;
    pending_event.address = address;
    pending_event.length  = length;
    pending_event.data    = data;

    pending_event.pending = 1;
}

static inline void mdt_event_clear(void)
{
    /* The other fields don't need clearing because are set before pending*/
    pending_event.pending = 0;
}

uint8_t mdt_event_pending(void)
{
    return pending_event.pending;
}

void mdt_event_send(void)
{
    if (!mdt_event_pending())
        return;

    uint8_t pkt[MDT_PACKET_SIZE];
    uint16_t crc;

    pkt[MDT_OFFSET_START] = MDT_START_BYTE;

    /* Must stay fixed */
    pkt[MDT_OFFSET_CMD_ID] = 0;
    pkt[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_EVENT;

    /* Free fields */
    pkt[MDT_OFFSET_SEQ]    = pending_event.seq;
    pkt[MDT_OFFSET_MEM_ID] = pending_event.mem_id;

    /* ADDRESS */
    pkt[MDT_OFFSET_ADDRESS]     = (uint8_t)(pending_event.address & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 1] = (uint8_t)((pending_event.address >> 8)  & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 2] = (uint8_t)((pending_event.address >> 16) & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 3] = (uint8_t)((pending_event.address >> 24) & 0xFF);

    /* LENGTH */
    pkt[MDT_OFFSET_LENGTH]     = (uint8_t)(pending_event.length & 0xFF);
    pkt[MDT_OFFSET_LENGTH + 1] = (uint8_t)((pending_event.length >> 8)  & 0xFF);

    /* Full 32-bit event data in data field (little-endian) */
    pkt[MDT_OFFSET_DATA]     = (uint8_t)(pending_event.data & 0xFF);
    pkt[MDT_OFFSET_DATA + 1] = (uint8_t)((pending_event.data >> 8)  & 0xFF);
    pkt[MDT_OFFSET_DATA + 2] = (uint8_t)((pending_event.data >> 16) & 0xFF);
    pkt[MDT_OFFSET_DATA + 3] = (uint8_t)((pending_event.data >> 24) & 0xFF);

    pkt[MDT_OFFSET_END] = MDT_END_BYTE;

    crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_CRC_COVER_LEN  /* exclude START, CRC, END */
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);

    mdt_event_clear();
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

    buffer->fence_pre  = MDT_FENCE_PATTERN;
    buffer->fence_post = MDT_FENCE_PATTERN;

    uint8_t *p = buffer->buf;
    uint8_t  n = MDT_PACKET_SIZE;
    while (n--) *p++ = 0;
}

/* Shared guard: fence check + overflow check.
 * Returns 1 if buffer is healthy, 0 if a fault was detected and handled. */
static uint8_t mdt_buffer_guard(void)
{
    if (!mdt_buffer_check(&rx_packet) || hal_uart_rx_overflow())
    {
        mdt_buffer_reset(&rx_packet);

        mdt_event_set(
            0,                                  /* seq */
            INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, /* mem_id = event type */
            (uint32_t)(uintptr_t)&rx_packet,    /* address = buffer */
            sizeof(rx_packet),                  /* length */
            0                                   /* data */
        );

        return 0;
    }

    return 1;
}

static void mdt_send_nack(const uint8_t *buf)
{
    uint8_t pkt[MDT_PACKET_SIZE];
 
    pkt[MDT_OFFSET_START]  = MDT_START_BYTE;
    pkt[MDT_OFFSET_CMD_ID] = 0;
    pkt[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_ACK_NACK | INTERNAL_MDT_FLAG_STATUS_ERROR;
    pkt[MDT_OFFSET_SEQ]    = buf[MDT_OFFSET_SEQ];
    pkt[MDT_OFFSET_MEM_ID] = 0;
 
    pkt[MDT_OFFSET_ADDRESS]     = 0;
    pkt[MDT_OFFSET_ADDRESS + 1] = 0;
    pkt[MDT_OFFSET_ADDRESS + 2] = 0;
    pkt[MDT_OFFSET_ADDRESS + 3] = 0;
 
    pkt[MDT_OFFSET_LENGTH]      = 0;
    pkt[MDT_OFFSET_LENGTH + 1]  = 0;
 
    pkt[MDT_OFFSET_DATA]        = 0;
    pkt[MDT_OFFSET_DATA + 1]    = 0;
    pkt[MDT_OFFSET_DATA + 2]    = 0;
    pkt[MDT_OFFSET_DATA + 3]    = 0;
 
    uint16_t crc = mdt_crc16(
        &pkt[MDT_OFFSET_CMD_ID],
        MDT_CRC_COVER_LEN  /* exclude START, CRC, END */
    );

    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);
 
    pkt[MDT_OFFSET_END] = MDT_END_BYTE;
 
    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);
}

/* Handle a full packet. Returns 1 if success, 0 if fence/critical error */
static uint8_t mdt_handle_packet(mdt_buffer_t *buf)
{
    /* Validate packet */
    uint8_t *pkt = buf->buf;
    if (!mdt_packet_validate(pkt, MDT_PACKET_SIZE))
    {
        mdt_send_nack(pkt); /* Send NACK so PC knows to retransmit */

        mdt_event_set(
            0,                               /* seq */
            INTERNAL_MDT_EVENT_FAILED_PACKET,/* mem_id = event type */
            (uint32_t)(uintptr_t)buf,        /* address = buffer address */
            MDT_PACKET_SIZE,                 /* length = expected packet size */
            0                                /* data = debug info */
        );

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
        MDT_CRC_COVER_LEN
    );
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    /* Send response */
    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);

    /* Reset buffer for next packet */
    mdt_buffer_reset(buf);

    return 1;
}

/* Process one byte */
static void mdt_process_byte(uint8_t byte)
{
    /* Wait for START byte */
    if (!rx_packet.started)
    {
        if (byte != MDT_START_BYTE)
            return;
        rx_packet.started = 1;
        rx_packet.idx = 0;
        rx_packet.buf[rx_packet.idx++] = byte;
        return;
    }

    /* Prevent buffer overflow */
    if (rx_packet.idx >= MDT_PACKET_SIZE)
    {

        mdt_event_set(
            0,                                  /* seq */
            INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, /* mem_id = event type */
            (uint32_t)(uintptr_t)&rx_packet,    /* address = buffer */
            MDT_PACKET_SIZE,                    /* length = capacity */
            rx_packet.idx                       /* data = overflow index */
        );

        mdt_buffer_reset(&rx_packet);

        return;
    }

    /* Store byte */
    rx_packet.buf[rx_packet.idx++] = byte;
    if (rx_packet.idx == MDT_PACKET_SIZE)
        mdt_handle_packet(&rx_packet);
}

#if MDT_FEATURE_UART_IDLE
/* Drain the RX ring buffer: called from USART IDLE ISR on STM32 via PendSV.
 * Processes one byte at a time through mdt_process_byte.
 * Not used on AVR where mcu_mdt_poll() is called from the main loop. */
static void mdt_process_pending(void)
{
    uint8_t byte;

    if (!mdt_buffer_guard())
        return;

    while (hal_uart_rx(&byte))
        mdt_process_byte(byte);
}

uint8_t mdt_event_fill_buf(uint8_t *buf)
{
    mcu_mdt_watchpoint_check();

    if (!mdt_event_pending())
        return 1; /* no event — clean ACK, no payload */

    buf[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_EVENT;
    buf[MDT_OFFSET_SEQ]    = pending_event.seq;
    buf[MDT_OFFSET_MEM_ID] = pending_event.mem_id;

    buf[MDT_OFFSET_ADDRESS]     = (uint8_t)(pending_event.address & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 1] = (uint8_t)((pending_event.address >> 8)  & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 2] = (uint8_t)((pending_event.address >> 16) & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 3] = (uint8_t)((pending_event.address >> 24) & 0xFF);

    buf[MDT_OFFSET_LENGTH]     = (uint8_t)(pending_event.length & 0xFF);
    buf[MDT_OFFSET_LENGTH + 1] = (uint8_t)((pending_event.length >> 8)  & 0xFF);

    buf[MDT_OFFSET_DATA]     = (uint8_t)(pending_event.data & 0xFF);
    buf[MDT_OFFSET_DATA + 1] = (uint8_t)((pending_event.data >> 8)  & 0xFF);
    buf[MDT_OFFSET_DATA + 2] = (uint8_t)((pending_event.data >> 16) & 0xFF);
    buf[MDT_OFFSET_DATA + 3] = (uint8_t)((pending_event.data >> 24) & 0xFF);

    mdt_event_clear();
    return 1;
}
#endif

void mcu_mdt_init(void)
{
    /* Initialization code for MCU MDT */
    hal_uart_init();
#if MDT_FEATURE_UART_IDLE
    hal_uart_set_idle_callback(mdt_process_pending);
#endif
}

/* Poll function — call from your main loop. */
void mcu_mdt_poll(void)
{
    uint8_t byte;

    /* 1. Flush pending event — only if TX is fully idle so the event packet
     *    never interleaves with a response still draining through the ISR. */
    if (mdt_event_pending() && hal_uart_tx_empty())
        mdt_event_send();

    /* 2. Guard: fence + overflow check */
    if (!mdt_buffer_guard())
        return;

    /* 3. Drain RX ring buffer fully */
    while (hal_uart_rx(&byte))
        mdt_process_byte(byte);

    /* 4. Watchpoints last — event stored here is sent on the next poll
     *    iteration once TX is confirmed idle at step 1. */
    mcu_mdt_watchpoint_check();
}
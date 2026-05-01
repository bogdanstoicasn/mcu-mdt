#include "mcu_mdt.h"
#include "mcu_mdt_event.h"
#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_watchpoint.h"

/* RX buffer */

typedef uint32_t mdt_fence_t;

typedef struct {
    mdt_fence_t fence_pre;

    uint8_t idx;
    uint8_t started;
    uint8_t buf[MDT_PACKET_SIZE];

    mdt_fence_t fence_post;
} mdt_buffer_t;

static mdt_buffer_t rx_packet = {
    .fence_pre  = MDT_FENCE_PATTERN,
    .idx        = 0,
    .started    = 0,
    .buf        = {0},
    .fence_post = MDT_FENCE_PATTERN
};

static uint8_t pending_reset = 0;

void mdt_request_reset(void)
{
    pending_reset = 1;
}

/* Buffer helpers */

static inline uint8_t mdt_buffer_check(const mdt_buffer_t *buffer)
{
    return (buffer->fence_pre  == MDT_FENCE_PATTERN)
        && (buffer->fence_post == MDT_FENCE_PATTERN);
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

/* Fence + overflow guard.
 * Returns 1 if the buffer is healthy, 0 if a fault was detected and reset. */
static uint8_t mdt_buffer_guard(void)
{
    if (!mdt_buffer_check(&rx_packet) || hal_uart_rx_overflow())
    {
        mdt_buffer_reset(&rx_packet);

        mdt_event_set(
            0,                                  /* seq              */
            INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, /* mem_id = type    */
            (uint32_t)(uintptr_t)&rx_packet,    /* address = buffer */
            sizeof(rx_packet),                  /* length           */
            0                                   /* data             */
        );

        return 0;
    }

    return 1;
}


/* Packet handling */

static void mdt_send_nack(const uint8_t *buf)
{
    uint8_t pkt[MDT_PACKET_SIZE];

    pkt[MDT_OFFSET_START]       = MDT_START_BYTE;
    pkt[MDT_OFFSET_CMD_ID]      = 0;
    pkt[MDT_OFFSET_FLAGS]       = INTERNAL_MDT_FLAG_ACK_NACK | INTERNAL_MDT_FLAG_STATUS_ERROR;
    pkt[MDT_OFFSET_SEQ]         = buf[MDT_OFFSET_SEQ];
    pkt[MDT_OFFSET_MEM_ID]      = 0;
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
    pkt[MDT_OFFSET_END]         = MDT_END_BYTE;

    uint16_t crc = mdt_crc16(&pkt[MDT_OFFSET_CMD_ID], MDT_CRC_COVER_LEN);
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);
}

/* Handle one complete packet: validate - dispatch - ACK/NACK - send. */
static uint8_t mdt_handle_packet(mdt_buffer_t *buf)
{
    uint8_t *pkt = buf->buf;

    if (!mdt_packet_validate(pkt, MDT_PACKET_SIZE))
    {
        mdt_send_nack(pkt);

        mdt_event_set(
            0,
            INTERNAL_MDT_EVENT_FAILED_PACKET,
            (uint32_t)(uintptr_t)buf,
            MDT_PACKET_SIZE,
            0
        );

        mdt_buffer_reset(buf);
        return 0;
    }

    uint8_t status = mdt_dispatch(pkt);

    pkt[MDT_OFFSET_FLAGS] |= INTERNAL_MDT_FLAG_ACK_NACK;
    if (!status)
        pkt[MDT_OFFSET_FLAGS] |= INTERNAL_MDT_FLAG_STATUS_ERROR;

    uint16_t crc = mdt_crc16(&pkt[MDT_OFFSET_CMD_ID], MDT_CRC_COVER_LEN);
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);

    mdt_buffer_reset(buf);

    if (pending_reset)
        hal_reset(); /* drains TX then resets — does not return */

    return 1;
}

/* Feed one byte into the packet assembler. */
static void mdt_process_byte(uint8_t byte)
{
    if (!rx_packet.started)
    {
        if (byte != MDT_START_BYTE)
            return;
        rx_packet.started              = 1;
        rx_packet.idx                  = 0;
        rx_packet.buf[rx_packet.idx++] = byte;
        return;
    }

    if (rx_packet.idx >= MDT_PACKET_SIZE)
    {
        mdt_event_set(
            0,
            INTERNAL_MDT_EVENT_BUFFER_OVERFLOW,
            (uint32_t)(uintptr_t)&rx_packet,
            MDT_PACKET_SIZE,
            rx_packet.idx
        );

        mdt_buffer_reset(&rx_packet);
        return;
    }

    rx_packet.buf[rx_packet.idx++] = byte;

    if (rx_packet.idx == MDT_PACKET_SIZE)
        mdt_handle_packet(&rx_packet);
}

/* Interrupt-mode RX drain (STM32 only) */

#if MDT_FEATURE_UART_IDLE
/* Called from PendSV after the USART IDLE interrupt fires.
 * Drains the RX ring buffer; the poll packet (CMD_ID=0) drives event delivery. */
static void mdt_process_pending(void)
{
    uint8_t byte;

    if (!mdt_buffer_guard())
        return;

    while (hal_uart_rx(&byte))
        mdt_process_byte(byte);
}
#endif


/* Public API */

void mcu_mdt_init(void)
{
    hal_uart_init();
#if MDT_FEATURE_UART_IDLE
    hal_uart_set_idle_callback(mdt_process_pending);
#endif
}

/* Poll mode — call from your main loop (AVR, or STM32 with UART IDLE off). */
void mcu_mdt_poll(void)
{
    uint8_t byte;

    /* 1. Flush any pending event once TX is idle. */
    if (mdt_event_pending() && hal_uart_tx_empty())
        mdt_event_send();

    /* 2. Fence + overflow guard. */
    if (!mdt_buffer_guard())
        return;

    /* 3. Drain RX ring buffer. */
    while (hal_uart_rx(&byte))
        mdt_process_byte(byte);

    /* 4. Check watchpoints — event fires on next iteration at step 1. */
    mcu_mdt_watchpoint_check();
}
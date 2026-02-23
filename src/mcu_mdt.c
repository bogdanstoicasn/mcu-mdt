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

/* Handle a full packet. Returns 1 if success, 0 if fence/critical error */
static uint8_t mdt_handle_packet(mdt_buffer_t *buf)
{
    /* --- Fence check --- */
    if (!mdt_buffer_check(buf))
    {
        mdt_buffer_reset(buf);
        return 0; // stop processing
    }

    /* --- Validate packet --- */
    if (!mdt_packet_validate(buf->buf, MDT_PACKET_SIZE))
    {
        mdt_buffer_reset(buf);
        return 0;
    }

    /* --- Dispatch command --- */
    uint8_t status = mdt_dispatch(buf->buf);

    /* --- Set flags --- */
    buf->buf[MDT_OFFSET_FLAGS] |= MDT_FLAG_ACK_NACK;
    if (!status)
        buf->buf[MDT_OFFSET_FLAGS] |= MDT_FLAG_STATUS_ERROR;

    /* --- Recalculate CRC --- */
    uint16_t crc = mdt_crc16(
        &buf->buf[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE - 1 - 2 - 1
    );
    buf->buf[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    buf->buf[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    /* --- Send response --- */
    for (uint16_t i = 0; i < MDT_PACKET_SIZE; i++)
        hal_uart_tx(buf->buf[i]);

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

    /* --- Fence check at entry (optional) --- */
    if (!mdt_buffer_check(&rx_packet))
    {
        mdt_buffer_reset(&rx_packet);
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

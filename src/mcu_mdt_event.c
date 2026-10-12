#include "mcu_mdt_event.h"
#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt_watchpoint.h"

/* Error counters. Written only from the packet-processing context (PendSV in
 * interrupt mode, the main loop in poll mode), the same context that reports
 * them, so plain variables are enough. Saturate at 255. */
static uint8_t overflow_count;
static uint8_t failed_count;

void mdt_event_error(uint8_t type)
{
    uint8_t *count = (type == INTERNAL_MDT_EVENT_BUFFER_OVERFLOW) ? &overflow_count
                                                                  : &failed_count;
    if (*count != 0xFF)
        (*count)++;
}

static uint8_t take_error(uint8_t *count, uint8_t type, mdt_event_t *ev)
{
    if (!*count)
        return 0;

    ev->seq     = 0;
    ev->type    = type;
    ev->address = 0;
    ev->length  = 0;
    ev->data    = *count;   /* how many since the last report */
    *count      = 0;
    return 1;
}

static uint8_t take_breakpoint(mdt_event_t *ev)
{
    uint8_t id, hits;

    if (!mdt_breakpoint_take_hit(&id, &hits))
        return 0;

    ev->seq     = id;
    ev->type    = INTERNAL_MDT_EVENT_BREAKPOINT_HIT;
    ev->address = 0;
    ev->length  = 0;
    ev->data    = hits;     /* total hits */
    return 1;
}

static uint8_t take_watchpoint(mdt_event_t *ev)
{
    uint8_t  slot;
    uint32_t old_value, new_value;

    if (!mdt_watchpoint_take_change(&slot, &old_value, &new_value))
        return 0;

    ev->seq     = slot;
    ev->type    = INTERNAL_MDT_EVENT_WATCHPOINT_HIT;
    ev->address = old_value;
    ev->length  = 4;        /* uint32 */
    ev->data    = new_value;
    return 1;
}

uint8_t mdt_event_next(mdt_event_t *ev)
{
    return take_breakpoint(ev)
        || take_watchpoint(ev)
        || take_error(&overflow_count, INTERNAL_MDT_EVENT_BUFFER_OVERFLOW, ev)
        || take_error(&failed_count,   INTERNAL_MDT_EVENT_FAILED_PACKET,   ev);
}

/* Serialize the event payload fields into a packet buffer. */
static void encode(const mdt_event_t *e, uint8_t *buf)
{
    buf[MDT_OFFSET_SEQ]    = e->seq;
    buf[MDT_OFFSET_MEM_ID] = e->type;

    for (uint8_t i = 0; i < 4; i++)
    {
        buf[MDT_OFFSET_ADDRESS + i] = (uint8_t)(e->address >> (8u * i));
        buf[MDT_OFFSET_DATA    + i] = (uint8_t)(e->data    >> (8u * i));
    }

    buf[MDT_OFFSET_LENGTH]     = (uint8_t)(e->length);
    buf[MDT_OFFSET_LENGTH + 1] = (uint8_t)(e->length >> 8);
}

void mdt_event_send(void)
{
    /* Never emit a partial packet: only transmit into an empty TX buffer. */
    if (!hal_uart_tx_empty())
        return;

    mdt_event_t e;
    if (!mdt_event_next(&e))
        return;

    uint8_t pkt[MDT_PACKET_SIZE];
    pkt[MDT_OFFSET_START]  = MDT_START_BYTE;
    pkt[MDT_OFFSET_CMD_ID] = 0;
    pkt[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_EVENT;
    encode(&e, pkt);
    pkt[MDT_OFFSET_END] = MDT_END_BYTE;

    uint16_t crc = mdt_crc16(&pkt[MDT_OFFSET_CMD_ID], MDT_CRC_COVER_LEN);
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);
}

/* CMD_ID=0 poll response — only needed in interrupt mode.
 * mdt_handle_packet() stamps FLAG_ACK_NACK and recomputes the CRC after this
 * returns, so neither is done here. */
#if MDT_FEATURE_UART_IDLE
uint8_t mdt_event_fill_buf(uint8_t *buf)
{
    mdt_event_t e;

    if (mdt_event_next(&e))
    {
        buf[MDT_OFFSET_FLAGS] = INTERNAL_MDT_FLAG_EVENT;
        encode(&e, buf);
    }
    return 1; /* nothing pending: plain ACK, buffer untouched */
}
#endif

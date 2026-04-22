#include "mcu_mdt_event.h"
#include "mcu_mdt_protocol.h"
#include "mcu_mdt_watchpoint.h"
#include "mcu_mdt_hal.h"

/* Event state — private to this translation unit */
typedef struct {
    uint32_t address;
    uint32_t data;
    uint16_t length;
    uint8_t  seq;
    uint8_t  mem_id;

    volatile uint8_t pending;
} mdt_event_t;

static mdt_event_t pending_event = { 0 };

void mdt_event_set(
    uint8_t  seq,
    uint8_t  mem_id,
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
    /* Other fields don't need clearing — they are always set before pending. */
    pending_event.pending = 0;
}

uint8_t mdt_event_pending(void)
{
    return pending_event.pending;
}

/* Serialize pending_event into a raw packet and transmit it. */
void mdt_event_send(void)
{
    if (!mdt_event_pending())
        return;

    uint8_t  pkt[MDT_PACKET_SIZE];
    uint16_t crc;

    pkt[MDT_OFFSET_START]  = MDT_START_BYTE;
    pkt[MDT_OFFSET_CMD_ID] = 0;
    pkt[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_EVENT;
    pkt[MDT_OFFSET_SEQ]    = pending_event.seq;
    pkt[MDT_OFFSET_MEM_ID] = pending_event.mem_id;

    pkt[MDT_OFFSET_ADDRESS]     = (uint8_t)(pending_event.address        & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 1] = (uint8_t)((pending_event.address >> 8)  & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 2] = (uint8_t)((pending_event.address >> 16) & 0xFF);
    pkt[MDT_OFFSET_ADDRESS + 3] = (uint8_t)((pending_event.address >> 24) & 0xFF);

    pkt[MDT_OFFSET_LENGTH]     = (uint8_t)(pending_event.length       & 0xFF);
    pkt[MDT_OFFSET_LENGTH + 1] = (uint8_t)((pending_event.length >> 8) & 0xFF);

    pkt[MDT_OFFSET_DATA]     = (uint8_t)(pending_event.data        & 0xFF);
    pkt[MDT_OFFSET_DATA + 1] = (uint8_t)((pending_event.data >> 8)  & 0xFF);
    pkt[MDT_OFFSET_DATA + 2] = (uint8_t)((pending_event.data >> 16) & 0xFF);
    pkt[MDT_OFFSET_DATA + 3] = (uint8_t)((pending_event.data >> 24) & 0xFF);

    pkt[MDT_OFFSET_END] = MDT_END_BYTE;

    crc = mdt_crc16(&pkt[MDT_OFFSET_CMD_ID], MDT_CRC_COVER_LEN);
    pkt[MDT_OFFSET_CRC]     = (uint8_t)(crc);
    pkt[MDT_OFFSET_CRC + 1] = (uint8_t)(crc >> 8);

    hal_uart_tx_buf(pkt, MDT_PACKET_SIZE);

    mdt_event_clear();
}

/* CMD_ID=0 poll response — only needed in interrupt mode.
 * Checks watchpoints first, then fills buf[] in-place with the event payload.
 * mdt_handle_packet() stamps FLAG_ACK_NACK and recalculates the CRC after
 * this returns, so we must not do either here. */
#if MDT_FEATURE_UART_IDLE
uint8_t mdt_event_fill_buf(uint8_t *buf)
{
    if (!mdt_event_pending())
        return 1; /* no event — plain ACK, buffer untouched */

    buf[MDT_OFFSET_FLAGS]  = INTERNAL_MDT_FLAG_EVENT;
    buf[MDT_OFFSET_SEQ]    = pending_event.seq;
    buf[MDT_OFFSET_MEM_ID] = pending_event.mem_id;

    buf[MDT_OFFSET_ADDRESS]     = (uint8_t)(pending_event.address        & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 1] = (uint8_t)((pending_event.address >> 8)  & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 2] = (uint8_t)((pending_event.address >> 16) & 0xFF);
    buf[MDT_OFFSET_ADDRESS + 3] = (uint8_t)((pending_event.address >> 24) & 0xFF);

    buf[MDT_OFFSET_LENGTH]     = (uint8_t)(pending_event.length       & 0xFF);
    buf[MDT_OFFSET_LENGTH + 1] = (uint8_t)((pending_event.length >> 8) & 0xFF);

    buf[MDT_OFFSET_DATA]     = (uint8_t)(pending_event.data        & 0xFF);
    buf[MDT_OFFSET_DATA + 1] = (uint8_t)((pending_event.data >> 8)  & 0xFF);
    buf[MDT_OFFSET_DATA + 2] = (uint8_t)((pending_event.data >> 16) & 0xFF);
    buf[MDT_OFFSET_DATA + 3] = (uint8_t)((pending_event.data >> 24) & 0xFF);

    mdt_event_clear();
    return 1;
}
#endif
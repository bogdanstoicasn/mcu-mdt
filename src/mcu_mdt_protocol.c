#include "mcu_mdt_hal.h"
#include "mcu_mdt_event.h"
#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt_watchpoint.h"
#include "mcu_mdt_protocol.h"


uint16_t mdt_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;

    while (len--)
    {
        uint8_t x = (uint8_t)(crc >> 8) ^ *data++;
        x ^= (x >> 4);
        x &= 0xFF;
        crc = (crc << 8) ^ ((uint16_t)(x << 12)) ^ ((uint16_t)(x << 5)) ^ ((uint16_t)x);
    }

    return crc;
}

/* Little-endian decode helpers — used by every command handler */
static inline uint32_t mdt_get_u32(const uint8_t *p)
{
    return  (uint32_t)p[0]        |
           ((uint32_t)p[1] << 8)  |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static inline uint16_t mdt_get_u16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len)
{
    if (!buf || len != MDT_PACKET_SIZE)
        return 0;

    if (buf[MDT_OFFSET_START] != MDT_START_BYTE ||
        buf[MDT_OFFSET_END]   != MDT_END_BYTE)
        return 0;

    if (mdt_get_u16(&buf[MDT_OFFSET_LENGTH]) > MDT_DATA_MAX_SIZE)
        return 0;

    uint16_t crc_rx   = mdt_get_u16(&buf[MDT_OFFSET_CRC]);
    uint16_t crc_calc = mdt_crc16(&buf[MDT_OFFSET_CMD_ID], MDT_CRC_COVER_LEN);

    return (crc_rx == crc_calc);
}

/* Command handlers zone
 * Each handler receives the raw packet and extracts only what it needs.
 * This allows for more complex commands in the future without changing the dispatch logic.
 */
static uint8_t handle_reserved(uint8_t *buf)
{
#if MDT_FEATURE_UART_IDLE
    mcu_mdt_watchpoint_check();
    return mdt_event_fill_buf(buf);
#else
    (void)buf;
    return 0;
#endif
}

static uint8_t handle_read_mem(uint8_t *buf)
{
    return hal_read_memory(
        buf[MDT_OFFSET_MEM_ID],
        mdt_get_u32(&buf[MDT_OFFSET_ADDRESS]),
        &buf[MDT_OFFSET_DATA],
        mdt_get_u16(&buf[MDT_OFFSET_LENGTH])
    );
}

static uint8_t handle_write_mem(uint8_t *buf)
{
    return hal_write_memory(
        buf[MDT_OFFSET_MEM_ID],
        mdt_get_u32(&buf[MDT_OFFSET_ADDRESS]),
        &buf[MDT_OFFSET_DATA],
        mdt_get_u16(&buf[MDT_OFFSET_LENGTH])
    );
}

static uint8_t handle_read_reg(uint8_t *buf)
{
    return hal_read_register(mdt_get_u32(&buf[MDT_OFFSET_ADDRESS]), &buf[MDT_OFFSET_DATA]);
}

static uint8_t handle_write_reg(uint8_t *buf)
{
    return hal_write_register(mdt_get_u32(&buf[MDT_OFFSET_ADDRESS]), &buf[MDT_OFFSET_DATA]);
}

static uint8_t handle_ping(uint8_t *buf)
{
    (void)buf;
    return 1;
}

static uint8_t handle_reset(uint8_t *buf)
{
    (void)buf;
    return 0; /* not implemented */
}

static uint8_t handle_breakpoint(uint8_t *buf)
{
    /* mem_id = control, address field = slot ID */
    return mdt_breakpoint_dispatch(
        buf[MDT_OFFSET_MEM_ID],
        mdt_get_u32(&buf[MDT_OFFSET_ADDRESS])
    );
}

static uint8_t handle_watchpoint(uint8_t *buf)
{
    /* mem_id      = control (enable/disable/reset/set_mask)
     * address     = slot ID
     * data[0..3]  = watched address (enable) or mask value (set_mask)
     */
    return mdt_watchpoint_dispatch(
        buf[MDT_OFFSET_MEM_ID],
        (uint8_t)mdt_get_u32(&buf[MDT_OFFSET_ADDRESS]),
        mdt_get_u32(&buf[MDT_OFFSET_DATA])
    );
}

static const mdt_cmd_handler_t handlers[] = {
    [INTERNAL_MDT_CMD_NONE]       = handle_reserved, /* No command, should not be called */
    [INTERNAL_MDT_CMD_READ_MEM]   = handle_read_mem,
    [INTERNAL_MDT_CMD_WRITE_MEM]  = handle_write_mem,
    [INTERNAL_MDT_CMD_READ_REG]   = handle_read_reg,
    [INTERNAL_MDT_CMD_WRITE_REG]  = handle_write_reg,
    [INTERNAL_MDT_CMD_PING]       = handle_ping,
    [INTERNAL_MDT_CMD_RESET]      = handle_reset,
    [INTERNAL_MDT_CMD_BREAKPOINT] = handle_breakpoint,
    [INTERNAL_MDT_CMD_WATCHPOINT] = handle_watchpoint,
};

/* Execute the commands */
uint8_t mdt_dispatch(uint8_t *buf)
{
    if (!buf)
        return 0;

    uint8_t cmd_id = buf[MDT_OFFSET_CMD_ID];

    if (cmd_id >= sizeof(handlers) / sizeof(handlers[0]))
        return 0; /* Invalid command */

    return handlers[cmd_id](buf);
}

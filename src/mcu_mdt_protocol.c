#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"
#include "mcu_mdt_breakpoints.h"
#include "mcu_mdt_watchpoint.h"


uint16_t mdt_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    uint8_t x;

    while(len--)
    {
        x = crc >> 8 ^ *data++;
        x ^= x >> 4;
        crc = (crc << 8) ^ ((uint16_t)(x << 12)) ^ ((uint16_t)(x <<5)) ^ ((uint16_t)x);
    }

    return crc;
}

uint8_t mdt_packet_validate(const uint8_t *buf, uint16_t len)
{
    uint16_t crc_rx;
    uint16_t crc_calc;
    uint16_t length_field;

    if (!buf)
        return 0;

    if (len != MDT_PACKET_SIZE)
        return 0;

    /* START / END check */
    if (buf[MDT_OFFSET_START] != MDT_START_BYTE ||
        buf[MDT_OFFSET_END]   != MDT_END_BYTE)
        return 0;

    /* LENGTH field sanity */
    length_field =
        (uint16_t)buf[MDT_OFFSET_LENGTH] |
        ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);

    if (length_field > MDT_DATA_MAX_SIZE)
        return 0;

    /* CRC extraction */
    crc_rx =
        (uint16_t)buf[MDT_OFFSET_CRC] |
        ((uint16_t)buf[MDT_OFFSET_CRC + 1] << 8);

    /* CRC calculation */
    crc_calc = mdt_crc16(
        &buf[MDT_OFFSET_CMD_ID],
        MDT_PACKET_SIZE
            - 1 /* START */
            - 2 /* CRC */
            - 1 /* END */
    );

    return (crc_rx == crc_calc);
}

/* Command handlers zone
 * Each handlers receives the raw packet and extracts only what it needs.
 * This allows for more complex commands in the future without changing the dispatch logic.
 */
static uint8_t handle_reserved(uint8_t *buf)
{
    (void)buf;
    return 0;
}

static uint8_t handle_read_mem(uint8_t *buf)
{
    uint8_t mem_id = buf[MDT_OFFSET_MEM_ID];
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    uint16_t length =
        ((uint16_t)buf[MDT_OFFSET_LENGTH]) |
        ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);
    
    return hal_read_memory(mem_id, address, &buf[MDT_OFFSET_DATA], length);
}

static uint8_t handle_write_mem(uint8_t *buf)
{
    uint8_t mem_id = buf[MDT_OFFSET_MEM_ID];
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    uint16_t length =
        ((uint16_t)buf[MDT_OFFSET_LENGTH]) |
        ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);
    
    return hal_write_memory(mem_id, address, &buf[MDT_OFFSET_DATA], length);
}

static uint8_t handle_read_reg(uint8_t *buf)
{
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    
    return hal_read_register(address, &buf[MDT_OFFSET_DATA]);
}

static uint8_t handle_write_reg(uint8_t *buf)
{
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    
    return hal_write_register(address, &buf[MDT_OFFSET_DATA]);
}

static uint8_t handle_ping(uint8_t *buf)
{
    (void)buf; /* unused */
    return 1; /* always succeed */
}

static uint8_t handle_reset(uint8_t *buf)
{
    (void)buf; /* unused */
    return 0; /* not implemented */
}

static uint8_t handle_breakpoint(uint8_t *buf)
{
    uint8_t id = (uint8_t)buf[MDT_OFFSET_MEM_ID];
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    
    return mdt_breakpoint_dispatch(id, address);
}

static uint8_t handle_watchpoint(uint8_t *buf)
{
    /* mem_id   = control (enable/disable/reset/set_mask)
     * address  = slot ID
     * data[0..3] = watched address (enable) or mask value (set_mask)
     */
    uint8_t control = (uint8_t)buf[MDT_OFFSET_MEM_ID];
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    uint32_t payload =
        ((uint32_t)buf[MDT_OFFSET_DATA]) |
        ((uint32_t)buf[MDT_OFFSET_DATA + 1] << 8 ) |
        ((uint32_t)buf[MDT_OFFSET_DATA + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_DATA + 3] << 24);
    
    return mdt_watchpoint_dispatch(control, (uint8_t)address, payload);
}

static const mdt_cmd_handler_t handlers[MDT_CMD_COUNT] = {
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

    if (cmd_id >= MDT_CMD_COUNT || !handlers[cmd_id])
        return 0; /* Invalid command */

    return handlers[cmd_id](buf);
}

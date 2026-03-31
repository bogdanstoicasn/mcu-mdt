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

/* Execute the commands */
uint8_t mdt_dispatch(uint8_t *buf)
{
    uint8_t status = 0;
 
    if (!buf)
        return 0;
 
    uint8_t  cmd_id = buf[MDT_OFFSET_CMD_ID];
    uint8_t  mem_id = buf[MDT_OFFSET_MEM_ID];
    uint32_t address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS])       |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8)  |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);
    uint16_t length =
        ((uint16_t)buf[MDT_OFFSET_LENGTH]) |
        ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);
    uint8_t *data = &buf[MDT_OFFSET_DATA];
 
    switch (cmd_id)
    {
        case MDT_CMD_PING:
            status = 1;
            break;
 
        case MDT_CMD_READ_MEM:
            status = hal_read_memory(mem_id, address, data, length);
            break;
 
        case MDT_CMD_READ_REG:
            status = hal_read_register(address, data);
            break;
 
        case MDT_CMD_WRITE_MEM:
            status = hal_write_memory(mem_id, address, data, length);
            break;
 
        case MDT_CMD_WRITE_REG:
            status = hal_write_register(address, data);
            break;
 
        case MDT_CMD_BREAKPOINT:
            status = mdt_breakpoint_dispatch(mem_id, address);
            break;
 
        case MDT_CMD_WATCHPOINT:
            /* mem_id   = control (enable/disable/reset/set_mask)
             * address  = slot ID
             * data[0..3] = watched address (enable) or mask value (set_mask) */
            {
                uint32_t payload =
                    ((uint32_t)data[0])        |
                    ((uint32_t)data[1] <<  8)  |
                    ((uint32_t)data[2] << 16)  |
                    ((uint32_t)data[3] << 24);
                status = mdt_watchpoint_dispatch(mem_id, (uint8_t)address, payload);
            }
            break;
 
        default:
            status = 0;
            break;
    }

    return status;
}

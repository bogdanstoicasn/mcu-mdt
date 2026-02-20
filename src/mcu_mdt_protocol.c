#include "mcu_mdt_protocol.h"
#include "mcu_mdt_hal.h"

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

/* Decode a MDT packet from a buffer */
static void mdt_decode(const uint8_t *buf, mdt_packet_t *pkt)
{
    pkt->cmd_id = buf[MDT_OFFSET_CMD_ID];
    pkt->flags  = buf[MDT_OFFSET_FLAGS];
    pkt->seq    = buf[MDT_OFFSET_SEQ];
    pkt->mem_id = buf[MDT_OFFSET_MEM_ID];

    pkt->address =
        ((uint32_t)buf[MDT_OFFSET_ADDRESS]) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 1] << 8) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 2] << 16) |
        ((uint32_t)buf[MDT_OFFSET_ADDRESS + 3] << 24);

    pkt->length =
        ((uint16_t)buf[MDT_OFFSET_LENGTH]) |
        ((uint16_t)buf[MDT_OFFSET_LENGTH + 1] << 8);

    for (uint8_t i = 0; i < MDT_DATA_MAX_SIZE; i++)
        pkt->data[i] = buf[MDT_OFFSET_DATA + i];

    pkt->crc =
        ((uint16_t)buf[MDT_OFFSET_CRC]) |
        ((uint16_t)buf[MDT_OFFSET_CRC + 1] << 8);
}

/* Encode a MDT packet into a buffer */
static void mdt_encode(uint8_t *buf, const mdt_packet_t *pkt)
{
    buf[MDT_OFFSET_CMD_ID] = pkt->cmd_id;
    buf[MDT_OFFSET_FLAGS]  = pkt->flags;
    buf[MDT_OFFSET_SEQ]    = pkt->seq;
    buf[MDT_OFFSET_MEM_ID] = pkt->mem_id;

    buf[MDT_OFFSET_ADDRESS]     = (uint8_t)(pkt->address);
    buf[MDT_OFFSET_ADDRESS + 1] = (uint8_t)(pkt->address >> 8);
    buf[MDT_OFFSET_ADDRESS + 2] = (uint8_t)(pkt->address >> 16);
    buf[MDT_OFFSET_ADDRESS + 3] = (uint8_t)(pkt->address >> 24);

    buf[MDT_OFFSET_LENGTH]     = (uint8_t)(pkt->length);
    buf[MDT_OFFSET_LENGTH + 1] = (uint8_t)(pkt->length >> 8);

    for (uint8_t i = 0; i < MDT_DATA_MAX_SIZE; i++)
        buf[MDT_OFFSET_DATA + i] = pkt->data[i];
}


uint8_t mdt_dispatch(uint8_t *buf)
{
    mdt_packet_t pkt;
    uint8_t status = 0;

    if (!buf)
        return 0;

    /* Decode raw buffer */
    mdt_decode(buf, &pkt);

    switch (pkt.cmd_id)
    {
        case MDT_CMD_PING:
            return 1; /* Just ACK */

        case MDT_CMD_READ_MEM:
        {
            status = hal_read_memory(pkt.mem_id, pkt.address, pkt.data, pkt.length);
            if(!status)
                return 0; /* Read failed */
            mdt_encode(buf, &pkt); /* Reuse buffer for response */
            return 1;
        }

        default:
            return 0; /* Unknown command */
    }

    return 0;
}


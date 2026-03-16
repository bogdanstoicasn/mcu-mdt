#include "commands.h"

uint8_t read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length)
{
    if(!buffer || length == 0)
        return 0;

    switch(mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
        case MDT_MEM_ZONE_FLASH:
            for(uint16_t i = 0; i < length; i++)
                buffer[i] = *((volatile uint8_t *)(uintptr_t)(address + i));
            return 1;

        default:
            return 0;
    }
}

/* Flash programming functions */

/* Unlock the flash memory */
static inline void flash_unlock(void)
{
    if (FLASH->cr & FLASH_CR_LOCK)
    {
        FLASH->keyr = FLASH_KEY1;
        FLASH->keyr = FLASH_KEY2;
    }
}

/* Lock the flash memory to prevent accidental writes */
static inline void flash_lock(void)
{
    FLASH->cr |= FLASH_CR_LOCK;
}

/* Wait until the flash is not busy */
static inline void flash_wait_busy(void)
{
    while (FLASH->sr & FLASH_SR_BSY);
}

/* Clear flash status flags */
static inline void flash_clear_flags(void)
{
    FLASH->sr = FLASH_SR_PGERR | FLASH_SR_WRPTERR | FLASH_SR_EOP;
}

/* Check if a flash region is erased (all bytes are 0xFF) */
static uint8_t flash_is_erased(uint32_t address, uint16_t length)
{
    // flash can only change bits from 1->0, so area should be 0xFFFF first
    for (uint16_t i = 0; i < length; i += 2)
    {
        uint16_t current = *((volatile uint16_t *)(uintptr_t)(address + i));
        if (current != 0xFFFF)
            return 0;
    }
    return 1;
}

/* Write a half-word (16 bits) to flash */
static uint8_t flash_write_halfword(uint32_t address, uint16_t data)
{
    flash_wait_busy();
    flash_clear_flags();

    FLASH->cr |= FLASH_CR_PG;

    /* Half-word write, other width causes hard fault on Cortex-M0 */
    *((volatile uint16_t *)(uintptr_t)address) = data;

    flash_wait_busy();

    uint8_t ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  = FLASH_SR_EOP;
    FLASH->cr &= ~FLASH_CR_PG;

    return ok;
}

/* Write a word (32 bits) to flash by performing two half-word writes */
static uint8_t flash_write_word(uint32_t address, uint32_t data)
{
    // 32-bit writes must be aligned to 4 bytes
    if (address & 0x3)
        return 0;

    flash_unlock();

    // write lower 16 bits, then upper 16 bits
    uint8_t ok = flash_write_halfword(address,    (uint16_t)(data & 0xFFFF));
    if (ok)
        ok    = flash_write_halfword(address + 2, (uint16_t)(data >> 16));

    flash_lock();
    return ok;
}

uint8_t write_memory(uint8_t mem_zone, uint32_t address, const uint8_t *buffer, uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
            for (uint16_t i = 0; i < length; i++)
                *((volatile uint8_t *)(uintptr_t)(address + i)) = buffer[i];
            return 1;

        case MDT_MEM_ZONE_FLASH:
        {
            // flash writes should be aligned to 2 bytes
            if (address & 0x1)
                return 0;

            // don't write if target is not erased yet
            if (!flash_is_erased(address, length))
                return 0;

            if (length <= 2)
            {
                uint16_t hw;
                if (length == 2)
                    hw = (uint16_t)buffer[0] | ((uint16_t)buffer[1] << 8);
                else
                    hw = (uint16_t)buffer[0] | 0xFF00; // if only 1 byte, keep upper byte erased(0xFF)

                flash_unlock();
                uint8_t ok = flash_write_halfword(address, hw);
                flash_lock();
                return ok;
            }
            else
            {
                // build one 32-bit value from up to 4 input bytes
                uint32_t word = 0xFFFFFFFF;
                for (uint16_t i = 0; i < length && i < 4; i++)
                    word = (word & ~(0xFFUL << (i * 8))) | ((uint32_t)buffer[i] << (i * 8));

                return flash_write_word(address, word);
            }
        }

        default:
            return 0;
    }
}
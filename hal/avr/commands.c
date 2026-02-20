#include "commands.h"
#include <avr/io.h>
#include <avr/pgmspace.h>
#include <avr/eeprom.h>

/* Read memory from a specific mem zone 
 * buffer is 4 bytes long as per protocol */
uint8_t read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
            for (uint8_t i = 0; i < length; i++)
            {
                buffer[i] = *((volatile uint8_t *)(address + i));
            }
            return 1;
        
        case MDT_MEM_ZONE_FLASH:
            for (uint8_t i = 0; i < length; i++)
            {
                buffer[i] = pgm_read_byte((const void *)(address + i));
            }
            return 1;
        
        case MDT_MEM_ZONE_EEPROM:
            for (uint8_t i = 0; i < length; i++)
            {
                buffer[i] = eeprom_read_byte((const uint8_t *)(address + i));
            }
            return 1;
        
        default:
            return 0; /* Invalid memory zone */
    }

    return 0; /* Should never reach here */
}

uint32_t read_register(uint32_t address, uint8_t *buffer)
{
    if (!buffer)
        return 0;

    /* For AVR, registers are memory-mapped, so we can read them like normal memory */
    buffer[0] = *((volatile uint8_t *)(address));
    buffer[1] = 0; /* For simplicity, we return 4 bytes but AVR registers are typically 1 byte */
    buffer[2] = 0;
    buffer[3] = 0;
    return 1;
}
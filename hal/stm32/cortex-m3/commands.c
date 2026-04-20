#include "commands.h"
#include "mcu_mdt_config.h"

uint8_t read_memory(uint8_t mem_zone,
                    uint32_t address,
                    uint8_t *buffer,
                    uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
        case MDT_MEM_ZONE_FLASH:
            for (uint16_t i = 0; i < length; i++)
                buffer[i] = *((volatile uint8_t *)(uintptr_t)(address + i));
            return 1;

        default:
            return 0;
    }
}


uint8_t write_memory(uint8_t mem_zone,
                     uint32_t address,
                     const uint8_t *buffer,
                     uint16_t length)
{
    return 0;
}

#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

uint8_t read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length);

uint32_t read_register(uint32_t address, uint8_t *buffer);

#endif // COMMANDS_H
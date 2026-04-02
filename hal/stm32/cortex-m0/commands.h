#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/* Flash zone */
#define FLASH_REGISTER_BASE 0x40022000

typedef struct {
    volatile uint32_t acr;
    volatile uint32_t keyr;
    volatile uint32_t optkeyr;
    volatile uint32_t sr;
    volatile uint32_t cr;
    volatile uint32_t ar;
    volatile uint32_t RESERVED;
    volatile uint32_t obr;
    volatile uint32_t wrpr;
} flash_def_t;

#define FLASH ((volatile flash_def_t *) FLASH_REGISTER_BASE)

/* FLASH_SR bits */
#define FLASH_SR_BSY     (1 << 0)
#define FLASH_SR_PGERR   (1 << 2)
#define FLASH_SR_WRPTERR (1 << 4)
#define FLASH_SR_EOP     (1 << 5)

/* FLASH_CR bits */
#define FLASH_CR_PG      (1 << 0)
#define FLASH_CR_PER     (1 << 1)
#define FLASH_CR_MER     (1 << 2)
#define FLASH_CR_STRT    (1 << 6)
#define FLASH_CR_LOCK    (1 << 7)

/* Unlock keys */
#define FLASH_KEY1  0x45670123
#define FLASH_KEY2  0xCDEF89AB

/* End of Flash zone */

uint8_t read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length);

uint8_t write_memory(uint8_t mem_zone, uint32_t address, const uint8_t *buffer, uint16_t length);

#endif /* COMMANDS_H */
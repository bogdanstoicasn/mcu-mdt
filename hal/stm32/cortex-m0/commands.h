#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>

/* FLASH_PAGE_SIZE is injected by the build system via -DFLASH_PAGE_SIZE=...
 * in cortex-m0/Makefile. Values per RM0360 §3.1:
 *   0x400UL (1 KB) — F030x4, F030x6, F030x8, F070x6
 *   0x800UL (2 KB) — F030xC, F070xB
 * A missing define is a hard build error, not a silent wrong value. */
#ifndef FLASH_PAGE_SIZE
#  error "FLASH_PAGE_SIZE not defined — pass -DFLASH_PAGE_SIZE=<size> from the Makefile"
#endif

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
#define FLASH_SR_WRPRTERR (1 << 4)
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


#endif /* COMMANDS_H */
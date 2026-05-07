#ifndef COMMANDS_H
#define COMMANDS_H

#include <stdint.h>

#define FLASH_BASE  0x40022000UL

#ifndef FLASH_PAGE_SIZE
#  error "FLASH_PAGE_SIZE not defined — pass -DFLASH_PAGE_SIZE=<size> from the Makefile"
#endif
 
typedef struct {
    volatile uint32_t acr;      /* 0x00  Access control  */
    volatile uint32_t keyr;     /* 0x04  Unlock key      */
    volatile uint32_t optkeyr;  /* 0x08  Option key      */
    volatile uint32_t sr;       /* 0x0C  Status          */
    volatile uint32_t cr;       /* 0x10  Control         */
    volatile uint32_t ar;       /* 0x14  Address (erase) */
    volatile uint32_t reserved; /* 0x18  —               */
    volatile uint32_t obr;      /* 0x1C  Option byte     */
    volatile uint32_t wrpr;     /* 0x20  Write protect   */
} flash_def_t;
 
#define FLASH  ((volatile flash_def_t *) FLASH_BASE)
 
/* FLASH_SR — status bits (write-1-to-clear where noted) */
#define FLASH_SR_BSY      (1U << 0)  /* Busy (hardware clears when done)   */
#define FLASH_SR_PGERR    (1U << 2)  /* Programming error  (w1c)           */
#define FLASH_SR_WRPTERR  (1U << 4)  /* Write-protection error (w1c)       */
#define FLASH_SR_EOP      (1U << 5)  /* End of operation   (w1c)           */
 
/* FLASH_CR — control bits */
#define FLASH_CR_PG       (1U << 0)  /* Standard programming mode          */
#define FLASH_CR_PER      (1U << 1)  /* Page erase                         */
#define FLASH_CR_MER      (1U << 2)  /* Mass erase                         */
#define FLASH_CR_STRT     (1U << 6)  /* Start erase (set after PER/MER)    */
#define FLASH_CR_LOCK     (1U << 7)  /* Controller locked (clear by keying) */
 
/* Unlock key sequence */
#define RDPRT_KEY   0x00A5UL
#define FLASH_KEY1  0x45670123UL
#define FLASH_KEY2  0xCDEF89ABUL

/* XL-density dual-bank support (F103xF, F103xG only).
 * Bank 2 has its own set of flash control registers starting at offset 0x44
 * from FLASH_BASE (RM0008 Table 8). The flash_def_t struct covers bank 1;
 * bank 2 registers are accessed via direct volatile pointer macros below.
 *
 * Offset layout from FLASH_BASE:
 *   0x00–0x20  bank-1 registers (flash_def_t)
 *   0x24–0x43  reserved
 *   0x44       FLASH_KEYR2
 *   0x48       reserved
 *   0x4C       FLASH_SR2
 *   0x50       FLASH_CR2
 *   0x54       FLASH_AR2                                           */
#ifdef FLASH_XL_DENSITY
#define FLASH_KEYR2  (*((volatile uint32_t *)(FLASH_BASE + 0x44UL)))
#define FLASH_SR2    (*((volatile uint32_t *)(FLASH_BASE + 0x4CUL)))
#define FLASH_CR2    (*((volatile uint32_t *)(FLASH_BASE + 0x50UL)))
#define FLASH_AR2    (*((volatile uint32_t *)(FLASH_BASE + 0x54UL)))

/* First address belonging to bank 2 */
#define FLASH_BANK2_START  0x08080000UL
#endif /* FLASH_XL_DENSITY */

#endif /* COMMANDS_H */
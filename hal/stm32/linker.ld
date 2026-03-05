/* Universal STM32F030xx Linker Script for C-only projects
   Usage: pass -DMCU=F030F4, F030F2, F030F6, F030F8, F030C6, F030C8
*/

/* Default MCU */
#ifndef MCU
#define MCU F030F4
#endif

/* Flash and RAM sizes per MCU */
#if MCU == F030F2
  FLASH_SIZE = 4K;
  RAM_SIZE   = 2K;
#elif MCU == F030F4
  FLASH_SIZE = 16K;
  RAM_SIZE   = 4K;
#elif MCU == F030F6
  FLASH_SIZE = 32K;
  RAM_SIZE   = 4K;
#elif MCU == F030F8
  FLASH_SIZE = 64K;
  RAM_SIZE   = 8K;
#elif MCU == F030C6
  FLASH_SIZE = 32K;
  RAM_SIZE   = 4K;
#elif MCU == F030C8
  FLASH_SIZE = 64K;
  RAM_SIZE   = 8K;
#else
  #error "Unknown MCU. Define FLASH_SIZE and RAM_SIZE manually."
#endif

/* Memory regions */
MEMORY
{
    rom (rx)  : ORIGIN = 0x08000000, LENGTH = FLASH_SIZE
    ram (rwx) : ORIGIN = 0x20000000, LENGTH = RAM_SIZE
}

/* Entry point */
ENTRY(Reset_Handler)


SECTIONS
{

    /* Interrupt vector table */
    .isr_vector :
    {
        KEEP(*(.vectors))
        . = ALIGN(4);
    } > rom


    /* Program code */
    .text :
    {
        *(.text*)
        . = ALIGN(4);
    } > rom


    /* Read-only data */
    .rodata :
    {
        *(.rodata*)
        . = ALIGN(4);
    } > rom


    /* End of code marker (used by startup to copy .data) */
    . = ALIGN(4);
    _etext = .;


    /* Initialized data copied to RAM at startup */
    .data : AT(_etext)
    {
        . = ALIGN(4);
        _sdata = .;

        *(.data*)

        . = ALIGN(4);
        _edata = .;
    } > ram


    /* Zero-initialized data */
    .bss :
    {
        . = ALIGN(4);
        _sbss = .;

        *(.bss*)
        *(COMMON)

        . = ALIGN(4);
        _ebss = .;
    } > ram


    /* End of RAM sections */
    . = ALIGN(4);
    end = .;
}


/* Stack pointer placed at top of RAM */
PROVIDE(_stack = ORIGIN(ram) + LENGTH(ram));
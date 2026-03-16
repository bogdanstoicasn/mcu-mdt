/* Universal STM32F030xx Linker Script
   Usage: pass -DMCU_F030F4, -DMCU_F030F6, etc. to the linker
*/

#ifdef MCU_F030F4
  FLASH_SIZE = 16K;
  RAM_SIZE   = 4K;
#elif defined(MCU_F030F6) || defined(MCU_F030C6)
  FLASH_SIZE = 32K;
  RAM_SIZE   = 4K;
#elif defined(MCU_F030F8) || defined(MCU_F030C8)
  FLASH_SIZE = 64K;
  RAM_SIZE   = 8K;
#elif defined(MCU_F030CC)
  FLASH_SIZE = 256K;
  RAM_SIZE   = 32K;
#elif defined(MCU_F070F6) || defined(MCU_F070CB)
  FLASH_SIZE = 32K;
  RAM_SIZE   = 6K;
#elif defined(MCU_F070RB)
  FLASH_SIZE = 128K;
  RAM_SIZE   = 16K;
#else
  #error "Unknown MCU. Pass -DMCU_<name> to the linker. Example: -DMCU_F030F4"
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
/* Universal STM32F103xx Linker Script
   Usage: pass -DMCU_<variant> to the linker via LDFLAGS.

   Low-density (LD):
     -DMCU_F103x4   (16K Flash,   6K RAM)
     -DMCU_F103x6   (32K Flash,   6K RAM)

   Medium-density (MD):
     -DMCU_F103x8   (64K Flash,  20K RAM)   <-- e.g. STM32F103C8T6 (Blue Pill)
     -DMCU_F103xB   (128K Flash, 20K RAM)

   High-density (HD):
     -DMCU_F103xC   (256K Flash, 48K RAM)
     -DMCU_F103xD   (384K Flash, 64K RAM)
     -DMCU_F103xE   (512K Flash, 64K RAM)

   XL-density (XL):
     -DMCU_F103xF   (768K Flash, 96K RAM)
     -DMCU_F103xG   (1M Flash,   96K RAM)

   Example (CMake / Makefile):
     LDFLAGS += -DMCU_F103x8
*/

#if defined(MCU_F103x4)
  FLASH_SIZE = 16K;
  RAM_SIZE   = 6K;
#elif defined(MCU_F103x6)
  FLASH_SIZE = 32K;
  RAM_SIZE   = 6K;
#elif defined(MCU_F103x8)
  FLASH_SIZE = 64K;
  RAM_SIZE   = 20K;
#elif defined(MCU_F103xB)
  FLASH_SIZE = 128K;
  RAM_SIZE   = 20K;
#elif defined(MCU_F103xC)
  FLASH_SIZE = 256K;
  RAM_SIZE   = 48K;
#elif defined(MCU_F103xD)
  FLASH_SIZE = 384K;
  RAM_SIZE   = 64K;
#elif defined(MCU_F103xE)
  FLASH_SIZE = 512K;
  RAM_SIZE   = 64K;
#elif defined(MCU_F103xF)
  FLASH_SIZE = 768K;
  RAM_SIZE   = 96K;
#elif defined(MCU_F103xG)
  FLASH_SIZE = 1024K;
  RAM_SIZE   = 96K;
#else
  #error "Unknown MCU. Pass -DMCU_<name> to the linker. Example: -DMCU_F103x8"
#endif


MEMORY
{
    rom (rx)  : ORIGIN = 0x08000000, LENGTH = FLASH_SIZE
    ram (rwx) : ORIGIN = 0x20000000, LENGTH = RAM_SIZE
}


ENTRY(Reset_Handler)


SECTIONS
{
    .isr_vector :
    {
        KEEP(*(.vectors))
        . = ALIGN(4);
    } > rom


    .text :
    {
        *(.text*)
        . = ALIGN(4);
    } > rom


    .rodata :
    {
        *(.rodata*)
        . = ALIGN(4);
    } > rom


    .ARM.extab :
    {
        *(.ARM.extab*)
        . = ALIGN(4);
    } > rom

    .ARM.exidx :
    {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
        . = ALIGN(4);
    } > rom


    _etext = .;


    .data : AT(_etext)
    {
        . = ALIGN(4);
        _sdata = .;

        *(.data*)

        . = ALIGN(4);
        _edata = .;
    } > ram


    .bss :
    {
        . = ALIGN(4);
        _sbss = .;

        *(.bss*)
        *(COMMON)

        . = ALIGN(4);
        _ebss = .;
    } > ram


    . = ALIGN(4);
    end = .;
    _end = .;
}


PROVIDE(_stack = ORIGIN(ram) + LENGTH(ram));
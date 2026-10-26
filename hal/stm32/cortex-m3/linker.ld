/* STM32F103 linker script. memory.ld (regions flash and ram) is generated per part in build/<part>/. */

INCLUDE memory.ld

ENTRY(Reset_Handler)


SECTIONS
{
    .isr_vector :
    {
        KEEP(*(.vectors))
        . = ALIGN(4);
    } > flash


    .text :
    {
        *(.text*)
        . = ALIGN(4);
    } > flash


    .rodata :
    {
        *(.rodata*)
        . = ALIGN(4);
    } > flash


    .ARM.extab :
    {
        *(.ARM.extab*)
        . = ALIGN(4);
    } > flash

    .ARM.exidx :
    {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
        . = ALIGN(4);
    } > flash

    . = ALIGN(4);
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
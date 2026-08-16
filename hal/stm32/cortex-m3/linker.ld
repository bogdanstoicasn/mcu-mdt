/* Universal STM32F103xx Linker Script */

INCLUDE memory.ld

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
/* Universal STM32F030xx Linker Script */

INCLUDE memory.ld

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
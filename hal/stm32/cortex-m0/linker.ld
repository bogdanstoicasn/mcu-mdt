/* STM32F0 linker script. memory.ld (regions flash and ram) is generated per part in build/<part>/. */

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
    } > flash


    /* Program code */
    .text :
    {
        *(.text*)
        . = ALIGN(4);
    } > flash


    /* Read-only data */
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
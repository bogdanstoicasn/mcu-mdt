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


    /* C constructors are not run by the startup: refuse them instead of dropping them silently */
    .init_array :
    {
        KEEP(*(.init_array*))
    } > flash
    ASSERT(SIZEOF(.init_array) == 0, "__attribute__((constructor)) is not supported: call the init function from main()")


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


    /* RAM the startup neither copies nor zeroes: survives a reset. Before `end`, so the stack check counts it */
    .noinit (NOLOAD) :
    {
        . = ALIGN(4);
        *(.noinit*)
        . = ALIGN(4);
    } > ram


    /* End of RAM sections */
    . = ALIGN(4);
    end = .;

    PROVIDE(_min_stack_size = 0x200);
    ASSERT(end + _min_stack_size <= ORIGIN(ram) + LENGTH(ram),
           "Not enough RAM left for the stack: reduce RAM use or _min_stack_size")
}


/* Stack pointer placed at top of RAM */
PROVIDE(_stack = ORIGIN(ram) + LENGTH(ram));
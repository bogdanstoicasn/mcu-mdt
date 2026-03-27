# Troubleshooting / Development Notes

## Linker script preprocessing issue

### Problem

The preprocessor directives in the linker script were not being evaluated correctly, which led to wrong assumptions about memory layout and section placement.

### Cause

The linker was using the raw `.ld` file without preprocessing, so macros and conditionals were not resolved.

### Solution

- Generated a preprocessed version of the linker script  
- Used that preprocessed file during linking instead of the original one  

### Result

The linker now interprets everything correctly and the memory layout behaves as expected.

### Lesson

Linker scripts are not always preprocessed by default, so if you rely on macros or conditionals, you may need to preprocess them manually.


## Reset_Handler behavior without `noreturn, naked`

### Problem

The `Reset_Handler` did not behave correctly when the `naked` attribute was removed.

### Observation

Without `naked`, the compiler generated extra instructions (stack setup, function epilogue, return handling), which don’t make sense in a reset context.

### Interpretation

At reset, there is no valid stack and no return address, so normal function behavior breaks the startup sequence.

### Conclusion

This wasn’t a “bug” in the code itself, but rather a mismatch between what the compiler expects and how a Cortex-M actually starts execution.

### Lesson

Startup code needs to be written with a clear understanding that:
- there is no stack yet
- there is no caller
- and no return is expected


## UART clock / baud rate mismatch

### Problem

UART communication was unreliable and sometimes completely broken.

### Cause

I was using the wrong clock value when configuring the UART baud rate.

Instead of using the actual MCU clock (which defaults to 8 MHz on this setup), I assumed a different frequency. This resulted in incorrect timing and broken serial communication.

### Context

Everything was written in bare-metal C:
- no STM32CubeIDE  
- no HAL  
- all clock and peripheral setup was done manually  

### Debugging

This took quite a while to figure out. I used:
- `arm-none-eabi` tools to inspect behavior  
- `pyserial` and `minicom` to test communication  
- `OpenOCD` to read registers and verify the UART configuration directly on the MCU  
- even a multimeter to check if the TX/RX pins were actually toggling or just floating  

### Fix

- Verified the actual system clock  
- Corrected the UART baud rate calculation to match that clock  
- Re-tested communication  

### Result

UART became stable and worked as expected.

### Lesson

When working without a framework, you really need to double-check basic assumptions like clock speed. If the clock is wrong, everything that depends on timing (like UART) will fail in subtle ways.


## Cortex-M interrupt and USART issue

### Problem

UART worked inconsistently when using interrupts:
- sometimes no data received  
- sometimes TX interrupts didn’t trigger  
- pins looked inactive or stuck  

### Debugging

I tried a lot of things to isolate the issue:
- checked peripheral registers with `OpenOCD`  
- stepped through the code with a debugger  
- used `pyserial` and `minicom` to observe behavior from the PC side  
- measured the pins with a multimeter to see if they were actually switching or just floating  

### Cause

The issue was caused by incorrect interrupt setup, including:  
- wrong interrupt enable flags  
- issues in initialization order  
- possible clock or peripheral enable mistakes  

### Fix

I reworked the UART initialization to make sure everything was set up in the correct order:

- GPIO configured for alternate function (TX/RX)  
- USART clock enabled  
- correct baud rate set  
- interrupts enabled properly:
  - RX interrupt (`RXNEIE`)  
  - TX interrupt (`TXEIE`) when needed  
- NVIC interrupt enabled  

Interrupt handler:
- RX: pushes incoming bytes into a ring buffer  
- TX: sends data from the buffer when ready  
- also handles errors like overrun  

### Result

After this, UART communication became stable:
- interrupts fired correctly  
- data was transmitted and received reliably  
- pin behavior matched expectations  

### Lesson

On Cortex-M, interrupts are very sensitive to setup details. A small mistake in:
- NVIC  
- peripheral config  
- or clock setup  

can break everything without obvious errors.

Also, tools like `OpenOCD` are extremely helpful because they let you directly inspect what the MCU is actually doing.

#ifndef MCU_MDT_CONFIG_H
#define MCU_MDT_CONFIG_H


/* Non-overridable: protocol and hardware constants */
#define MDT_FENCE_PATTERN 0xA5A5A5A5

typedef enum {
    MDT_MEM_ZONE_SRAM   = 0x00,
    MDT_MEM_ZONE_FLASH  = 0x01,
    MDT_MEM_ZONE_EEPROM = 0x02
} mdt_mem_zone_t;

/* Defaults: do not modify */
#define MDT_DEFAULT_UART_BAUDRATE   19200

#define MDT_DEFAULT_UART_DATA_BITS  8

#define MDT_DEFAULT_UART_STOP_BITS  1

#define MDT_DEFAULT_UART_PARITY     0

#define MDT_DEFAULT_BUFFER_SIZE     64

#define MDT_DEFAULT_TIMEOUT_MS      1000

#define MDT_DEFAULT_F_CPU           16000000UL

#define MDT_DEFAULT_MAX_BREAKPOINTS 4

#define MDT_DEFAULT_MAX_WATCHPOINTS 4

#define MDT_DEFAULT_MAX_RETRIES     3

#ifndef NULL
    #define NULL ((void *)0)
#endif

/* MDT_USE_UART_IDLE: user preference (default: enabled when hw supports it).
 * Set to 0 in your Makefile (-DMDT_USE_UART_IDLE=0) to disable IDLE-interrupt
 * driven processing and use mcu_mdt_poll() from your main loop instead.
 * Useful on STM32 if your application uses HAL_Delay() or other blocking calls
 * that prevent timely polling — in that case leave this at 1 (default).
 * Has no effect on AVR: the hardware has no UART IDLE interrupt. */
#ifndef MDT_USE_UART_IDLE
#define MDT_USE_UART_IDLE 1
#endif
 
/* MDT_HAL_HAS_UART_IDLE: set by the HAL Makefile when the hardware supports
 * a UART IDLE interrupt. Do not define this yourself. */
#if defined(MDT_HAL_HAS_UART_IDLE) && MDT_USE_UART_IDLE
#define MDT_FEATURE_UART_IDLE 1
#else
#define MDT_FEATURE_UART_IDLE 0
#endif


/* User configuration: edit these */
#define MDT_UART_BAUDRATE   MDT_DEFAULT_UART_BAUDRATE

#define MDT_UART_DATA_BITS  MDT_DEFAULT_UART_DATA_BITS

#define MDT_UART_STOP_BITS  MDT_DEFAULT_UART_STOP_BITS

#define MDT_UART_PARITY     MDT_DEFAULT_UART_PARITY

#define MDT_BUFFER_SIZE     MDT_DEFAULT_BUFFER_SIZE

#define MDT_TIMEOUT_MS      MDT_DEFAULT_TIMEOUT_MS

#ifndef F_CPU
    #define F_CPU           MDT_DEFAULT_F_CPU
#endif
#define MDT_MAX_BREAKPOINTS MDT_DEFAULT_MAX_BREAKPOINTS

#define MDT_MAX_WATCHPOINTS MDT_DEFAULT_MAX_WATCHPOINTS

#define MDT_MAX_RETRIES     MDT_DEFAULT_MAX_RETRIES

/* Compile time configuration guards */
_Static_assert((MDT_BUFFER_SIZE & (MDT_BUFFER_SIZE - 1)) == 0,
               "MDT_BUFFER_SIZE must be a power of 2 (e.g. 32, 64, 128)");

_Static_assert(MDT_MAX_WATCHPOINTS <= 8,
              "MDT_MAX_WATCHPOINTS cannot exceed 8 (active_mask is uint8_t)");

_Static_assert(MDT_MAX_BREAKPOINTS <= 8,
              "MDT_MAX_BREAKPOINTS cannot exceed 8");

#endif /* MCU_MDT_CONFIG_H */
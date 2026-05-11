#ifndef MCU_MDT_H
#define MCU_MDT_H

#include <stdint.h>

/**
 * @brief Initialize the MDT module. Call this from your main initialization code.
 * @return None
 */
void mcu_mdt_init(void);

/**
 * @brief Poll mode — call from your main loop (AVR, or STM32 with UART IDLE off).
 * @return None
 */
void mcu_mdt_poll(void);

/**
 * @brief Sample all active watchpoints and fire an event if any have changed.
 * 
 * Call this from your main loop if using polling mode.
 * In UART_IDLE mode, this is checked using a periodic packet sent by the host, so you don't need to call this manually.
 * @return None
 */
void mcu_mdt_watchpoint_check(void);

/**
 * @brief Forward declaration for the breakpoint macro
 */
void mdt_breakpoint_trigger(uint8_t id);

/**
 * @brief User-facing macro to trigger a software breakpoint
 * @param id The ID of the breakpoint to trigger
 */
#define MDT_BREAKPOINT(id) \
    do { \
        mdt_breakpoint_trigger(id); \
    } while(0)

#endif // MCU_MDT_H
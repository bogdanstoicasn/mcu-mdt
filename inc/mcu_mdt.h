#ifndef MCU_MDT_H
#define MCU_MDT_H

#include <stdint.h>

/* Initializes the MCU MDT module */
void mcu_mdt_init(void);

/* Polling function must be called in the main loop */
void mcu_mdt_poll(void);

/* Forward declaration for the breakpoint macro */
void mdt_breakpoint_trigger(uint8_t id);

/* User-facing macro to trigger a software breakpoint */
#define MDT_BREAKPOINT(id) \
    do { \
        mdt_breakpoint_trigger(id); \
    } while(0)

#endif // MCU_MDT_H
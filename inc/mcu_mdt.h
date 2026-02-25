#ifndef MCU_MDT_H
#define MCU_MDT_H

/* Initializes the MCU MDT module */
void mcu_mdt_init(void);

/* Polling function must be called in the main loop */
void mcu_mdt_poll(void);

#define BREAKPOINT(id) mdt_breakpoint_trigger(id)

#endif // MCU_MDT_H
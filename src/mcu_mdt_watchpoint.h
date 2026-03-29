#ifndef MCU_MDT_WATCHPOINT_H
#define MCU_MDT_WATCHPOINT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint32_t address;
    uint32_t snapshot;
} mdt_watchpoint_t;

typedef struct {
    mdt_watchpoint_t slots[MDT_MAX_WATCHPOINTS];
    uint8_t          active_mask;
} mdt_watchpoint_state_t;

typedef enum {
    MDT_WP_DISABLE = 0,
    MDT_WP_ENABLE  = 1,
    MDT_WP_RESET   = 2,
} mdt_watchpoint_control_t;

/* If no active watchpoints, return fast */
void mdt_watchpoint_poll(void);
 
/* Dispatch function for watchpoint control commands */
uint8_t mdt_watchpoint_dispatch(uint8_t control, uint8_t id, uint32_t address);

#endif
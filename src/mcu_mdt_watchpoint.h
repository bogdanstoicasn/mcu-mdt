#ifndef MCU_MDT_WATCHPOINT_H
#define MCU_MDT_WATCHPOINT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint32_t address;
    uint32_t snapshot;
    uint32_t mask; /* only watch bits set in mask. Default: 0xFFFFFFFF */
} mdt_watchpoint_t;

typedef struct {
    mdt_watchpoint_t slots[MDT_MAX_WATCHPOINTS];
    uint8_t          active_mask;
} mdt_watchpoint_state_t;

typedef enum {
    INTERNAL_MDT_WP_DISABLE = 0,
    INTERNAL_MDT_WP_ENABLE  = 1,
    INTERNAL_MDT_WP_RESET   = 2,
    INTERNAL_MDT_WP_MASK    = 3,
} mdt_watchpoint_control_t;

#define INTERNAL_MDT_DEFAULT_WP_MASK 0xffffffff

/* Dispatch function for watchpoint control commands */
uint8_t mdt_watchpoint_dispatch(uint8_t control, uint8_t id, uint32_t address);

/* Check for change in watchpoitns */
void mcu_mdt_watchpoint_check(void);

#endif
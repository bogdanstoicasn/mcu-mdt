#ifndef MCU_MDT_BREAKPOINTS_H
#define MCU_MDT_BREAKPOINTS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint8_t hit_count;      /* count how many times this breakpoint was hit */
    uint8_t enabled  : 1;
    uint8_t next     : 1;   /* for "next breakpoint" functionality */
    uint8_t reserved : 6;
} mdt_breakpoint_t;

typedef struct {
    mdt_breakpoint_t  slots[MDT_MAX_BREAKPOINTS];
} mdt_breakpoint_state_t;

typedef enum {
    INTERNAL_MDT_BP_DISABLE = 0,
    INTERNAL_MDT_BP_ENABLE  = 1,
    INTERNAL_MDT_BP_RESET   = 2,
    INTERNAL_MDT_BP_NEXT    = 3
} mdt_breakpoint_control_t;

/* Internal function triggered by macro */
void mdt_breakpoint_trigger(uint8_t id);

/* Dispatch function for breakpoint control commands */
uint8_t mdt_breakpoint_dispatch(uint8_t cmd_id, uint32_t id);

#endif /* MCU_MDT_BREAKPOINTS_H */
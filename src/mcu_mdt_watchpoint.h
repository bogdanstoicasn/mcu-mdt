#ifndef MCU_MDT_WATCHPOINT_H
#define MCU_MDT_WATCHPOINT_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint32_t address;
    uint32_t snapshot;
    uint8_t enabled;
} mdt_watchpoint_t;

typedef enum {
    MDT_WP_DISABLE = 0,
    MDT_WP_ENABLE = 1
} mdt_watchpoint_control_t;

#endif
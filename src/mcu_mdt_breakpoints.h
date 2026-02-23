#ifndef MCU_MDT_BREAKPOINTS_H
#define MCU_MDT_BREAKPOINTS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint8_t enabled;   // 0 = disabled, 1 = enabled
} mdt_breakpoint_t;

#endif /* MCU_MDT_BREAKPOINTS_H */
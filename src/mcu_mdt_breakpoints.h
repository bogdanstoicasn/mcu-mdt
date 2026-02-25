#ifndef MCU_MDT_BREAKPOINTS_H
#define MCU_MDT_BREAKPOINTS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint8_t enabled;   // 0 = disabled, 1 = enabled
} mdt_breakpoint_t;

// Internal function triggered by macro
void mdt_breakpoint_trigger(uint8_t id);

void mdt_breakpoint_enable(uint8_t id);
void mdt_breakpoint_disable(uint8_t id);

#endif /* MCU_MDT_BREAKPOINTS_H */
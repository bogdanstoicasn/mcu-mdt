#include "mcu_mdt_watchpoint.h"
#include "mcu_mdt_private.h"

static volatile mdt_watchpoint_t watchpoints[MDT_MAX_WATCHPOINTS] = {MDT_WP_DISABLE};

static inline __attribute__((always_inline)) void mdt_watchpoint_enable(uint8_t id, uint32_t address)
{
    // TODO
}
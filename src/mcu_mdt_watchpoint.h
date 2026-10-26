#ifndef MCU_MDT_WATCHPOINT_H
#define MCU_MDT_WATCHPOINT_H

#include <stdint.h>

/** @brief Type definition for MDT watchpoint structure */
typedef struct {
    uint32_t address;
    uint32_t snapshot;
    uint32_t mask; /* only watch bits set in mask. Default: 0xFFFFFFFF */
} mdt_watchpoint_t;

/** @brief Type definition for MDT watchpoint state structure */
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

#define INTERNAL_MDT_DEFAULT_WP_MASK 0xFFFFFFFF

/** @brief Function to dispatch watchpoint control commands
 * @param control Watchpoint control command
 * @param id Watchpoint ID
 * @param address Watched address
 * @return 1 if the command was handled successfully, 0 otherwise
 */
uint8_t mdt_watchpoint_dispatch(uint8_t control, uint8_t id, uint32_t address);

/**
 * @brief Sample the active watchpoints. If one differs from the value last
 *        taken, return the slot, the old and the new value, and make the new
 *        value the reference. Lowest slot first. Several changes between two
 *        calls collapse into one (old = value at the last call, new = latest).
 * @return 1 if a change was taken, 0 if nothing changed.
 */
uint8_t mdt_watchpoint_take_change(uint8_t *slot, uint32_t *old_value, uint32_t *new_value);

#endif
#ifndef MCU_MDT_BREAKPOINTS_H
#define MCU_MDT_BREAKPOINTS_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/**
 * @brief Structure representing a single breakpoint.
 */
typedef struct {
    volatile uint8_t hit_count;     /* hits so far. Written ONLY by the code that hit the breakpoint */
    uint8_t hit_reported;           /* hit_count as last reported. Written ONLY by the event reporter */
    volatile uint8_t enabled  : 1;
    volatile uint8_t next     : 1;   /* for "next breakpoint" functionality */
    uint8_t reserved : 6;
} mdt_breakpoint_t;

/**
 * @brief Structure representing the state of all breakpoints.
 */
typedef struct {
    mdt_breakpoint_t  slots[MDT_MAX_BREAKPOINTS];
} mdt_breakpoint_state_t;

/**
 * @brief Enum representing the control commands for breakpoints.
 */
typedef enum {
    INTERNAL_MDT_BP_DISABLE = 0,
    INTERNAL_MDT_BP_ENABLE  = 1,
    INTERNAL_MDT_BP_RESET   = 2,
    INTERNAL_MDT_BP_NEXT    = 3
} mdt_breakpoint_control_t;

/**
 * @brief Type definition for the breakpoint handler function.
 */
typedef void (*mdt_breakpoint_handler_t)(uint8_t id);

/**
 * @brief Internal function triggered by macro.
 * @param id Breakpoint ID.
 */
void mdt_breakpoint_trigger(uint8_t id);

/**
 * @brief Dispatch function for breakpoint control commands.
 * @param control Control command.
 * @param id Breakpoint ID.
 * @return Status of the operation.
 */
uint8_t mdt_breakpoint_dispatch(uint8_t control, uint32_t id);

/**
 * @brief If a breakpoint has been hit since the last call, return its id and
 *        total hit count and mark that hit as taken. Lowest id first.
 * @param id   Receives the breakpoint id.
 * @param hits Receives the total number of hits (8-bit, wraps).
 * @return 1 if a new hit was taken, 0 if there is nothing new.
 */
uint8_t mdt_breakpoint_take_hit(uint8_t *id, uint8_t *hits);

#endif /* MCU_MDT_BREAKPOINTS_H */
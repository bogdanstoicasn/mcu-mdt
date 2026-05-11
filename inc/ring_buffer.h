#ifndef RING_BUFFER_H
#define RING_BUFFER_H

#include <stdint.h>
#include "mcu_mdt_config.h"

/**
 * @brief Simple ring buffer implementation for UART data.
 * The buffer size is defined by MDT_BUFFER_SIZE, which must be a power of two.
 * The buffer uses head and tail indices to manage data, and an overflow flag.
 */
typedef struct {
    uint8_t buf[MDT_BUFFER_SIZE];
    volatile uint16_t head;
    volatile uint16_t tail;
    volatile uint8_t overflow_flag;
} ring_buffer_t;

/**
 * @brief Pop a byte from the ring buffer.
 * @param rb Pointer to the ring buffer.
 * @param data Pointer to a byte where the popped data will be stored.
 * @return 1 if a byte was successfully popped, 0 if the buffer is empty
 */
static inline uint8_t rb_pop(ring_buffer_t *rb, uint8_t *data)
{
    if (rb->head == rb->tail)
        return 0;
    *data = rb->buf[rb->tail];
    rb->tail = (rb->tail + 1) & (MDT_BUFFER_SIZE - 1);
    return 1;
}

/**
 * @brief Push a byte into the ring buffer.
 * @param rb Pointer to the ring buffer.
 * @param data The byte to push into the buffer.
 * @return 1 if the byte was successfully pushed, 0 if the buffer is full
 */
static inline uint8_t rb_push(ring_buffer_t *rb, uint8_t data)
{
    uint16_t next_head = (rb->head + 1) & (MDT_BUFFER_SIZE - 1);
    if (next_head == rb->tail)
        return 0;
    rb->buf[rb->head] = data;
    rb->head = next_head;
    return 1;
}

/* Simple macros to avoid function call overhead */
#define rb_is_empty(rb) ((rb)->head == (rb)->tail)
#define rb_is_full(rb)  (((((rb)->head + 1) & (MDT_BUFFER_SIZE - 1)) == (rb)->tail))

#endif
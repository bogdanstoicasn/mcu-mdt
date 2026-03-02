// src/ring_buffer.h
#ifndef RING_BUFFER_H
#define RING_BUFFER_H

#include <stdint.h>
#include "mcu_mdt_config.h" // for MDT_RX_BUFFER_SIZE

typedef struct {
    uint8_t buf[MDT_RX_BUFFER_SIZE];
    volatile uint16_t head;
    volatile uint16_t tail;
} ring_buffer_t;

uint8_t rb_push(ring_buffer_t *rb, uint8_t data);
uint8_t rb_pop(ring_buffer_t *rb, uint8_t *data);

/* Simple macros to avoid function call overhead */
#define rb_is_empty(rb) ((rb)->head == (rb)->tail)
#define rb_is_full(rb)  (((((rb)->head + 1) & (MDT_RX_BUFFER_SIZE - 1)) == (rb)->tail))

#endif
#include "ring_buffer.h"

uint8_t rb_push(ring_buffer_t *rb, uint8_t data)
{
    uint8_t next_head = (rb->head + 1) & (MDT_BUFFER_SIZE - 1);

    if (next_head == rb->tail)
    {
        return 0; // Buffer full
    }

    rb->buf[rb->head] = data;
    rb->head = next_head;
    return 1; // Success
}

uint8_t rb_pop(ring_buffer_t *rb, uint8_t *data)
{
    if (rb->head == rb->tail)
    {
        return 0; // Buffer empty
    }

    *data = rb->buf[rb->tail];
    rb->tail = (rb->tail + 1) & (MDT_BUFFER_SIZE - 1);
    return 1; // Success
}

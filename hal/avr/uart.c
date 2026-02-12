#include <avr/io.h>
#include <avr/interrupt.h>
#include "uart.h"
#include "mcu_mdt_config.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0 };

static ring_buffer_t tx_buffer = { .head = 0, .tail = 0 };

static inline uint8_t rb_push(ring_buffer_t *rb, uint8_t data)
{
    uint8_t next_head = (rb->head + 1) % MDT_RX_BUFFER_SIZE;

    if (next_head == rb->tail)
    {
        return 0; // Buffer full
    }

    rb->buf[rb->head] = data;
    rb->head = next_head;
    return 1; // Success
}

static inline uint8_t rb_pop(ring_buffer_t *rb, uint8_t *data)
{
    if (rb->head == rb->tail)
    {
        return 0; // Buffer empty
    }

    *data = rb->buf[rb->tail];
    rb->tail = (rb->tail + 1) % MDT_RX_BUFFER_SIZE;
    return 1; // Success
}

static inline uint8_t rb_is_empty(ring_buffer_t *rb)
{
    return rb->head == rb->tail;
}

static inline uint8_t rb_is_full(ring_buffer_t *rb)
{
    return ((rb->head + 1) % MDT_RX_BUFFER_SIZE) == rb->tail;
}

/* UART */
void uart_init(uint32_t baudrate)
{
    uint16_t ubrr = (F_CPU / (16UL * baudrate)) - 1;

    UBRR0H = (uint8_t)(ubrr >> 8);
    UBRR0L = (uint8_t)ubrr;

    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);

    sei();
}

uint8_t uart_putc(uint8_t data)
{
    if (!rb_push(&tx_buffer, data))
    {
        return 0; // Buffer full, drop data
    }
    
    UCSR0B |= (1 << UDRIE0); // Enable Data Register Empty Interrupt

    return 1; // Success
}

uint8_t uart_getc_nonblocking(uint8_t *data)
{
    return rb_pop(&rx_buffer, data);
}

/* Interrupt Service Routines */

ISR(USART_RX_vect)
{
    rb_push(&rx_buffer, UDR0);
}

ISR(USART_UDRE_vect)
{
    uint8_t data;
    if (rb_pop(&tx_buffer, &data))
    {
        UDR0 = data; // Send next byte
    }
    else
    {
        UCSR0B &= ~(1 << UDRIE0); // No more data to send, disable interrupt
    }
}

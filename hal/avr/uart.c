#include "uart.h"
#include <avr/io.h>
#include <avr/interrupt.h>

#define UART_RX_BUF_SIZE 128

static volatile uint8_t rx_buf[UART_RX_BUF_SIZE];
static volatile uint8_t rx_head = 0;
static volatile uint8_t rx_tail = 0;

static inline void rx_push(uint8_t b)
{
    uint8_t next = (rx_head + 1) % UART_RX_BUF_SIZE;
    if (next != rx_tail) {
        rx_buf[rx_head] = b;
        rx_head = next;
    }
}

void uart_init(uint32_t baudrate)
{
    uint16_t ubrr = (F_CPU / (16UL * baudrate)) - 1;

    UBRR0H = (uint8_t)(ubrr >> 8);
    UBRR0L = (uint8_t)ubrr;

    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);

    sei();
}

void uart_putc(uint8_t data)
{
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = data;
}

int uart_getc_nonblocking(uint8_t *data)
{
    if (rx_head == rx_tail)
        return 0;

    *data = rx_buf[rx_tail];
    rx_tail = (rx_tail + 1) % UART_RX_BUF_SIZE;
    return 1;
}

ISR(USART_RX_vect)
{
    rx_push(UDR0);
}

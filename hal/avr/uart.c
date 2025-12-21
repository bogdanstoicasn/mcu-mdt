#include <avr/io.h>
#include <avr/interrupt.h>
#include "uart.h"

void hal_uart_init(void)
{
    // 9600 baud @ 16MHz (temporary, hardcoded for now)
    UBRR0H = 0;
    UBRR0L = 103;

    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);

    sei();
}

void hal_uart_tx(uint8_t b)
{
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = b;
}

ISR(USART_RX_vect)
{
    uint8_t b = UDR0;

    // TEMPORARY TEST: echo
    hal_uart_tx(b);
}


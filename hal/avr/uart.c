#include <avr/io.h>
#include <avr/interrupt.h>
#include "uart.h"
#include "ring_buffer.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0 };

static ring_buffer_t tx_buffer = { .head = 0, .tail = 0 };

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
        return 0; /* Drop data */
    }
    
    UCSR0B |= (1 << UDRIE0); /* Enable data registry interrupt*/

    return 1;
}

uint8_t uart_getc_nonblocking(uint8_t *data)
{
    return rb_pop(&rx_buffer, data);
}

uint8_t uart_ready(void)
{
    return !rb_is_full(&tx_buffer);
}

/* Returns 1 and clears the flag if an RX overflow occurred since the last
 * call.  Called from mcu_mdt_poll() to surface dropped bytes as an event. */
uint8_t uart_rx_overflow(void)
{
    if (rx_buffer.overflow_flag)
    {
        rx_buffer.overflow_flag = 0;
        return 1;
    }

    return 0;
}

/* Interrupt Service Routines */

/* Vector Definitions Portability */
#if defined(USART_RX_vect)        /* Single UART MCUs (e.g., ATmega328P, ATmega168) */
    #define USART_RX_vect_name    USART_RX_vect
    #define USART_UDRE_vect_name  USART_UDRE_vect
#elif defined(USART0_RX_vect)     /* Multi-UART MCUs (e.g., ATmega2560, ATmega1280) */
    #define USART_RX_vect_name    USART0_RX_vect
    #define USART_UDRE_vect_name  USART0_UDRE_vect
#elif defined(USARTE_RX_vect)     /* Some ATtiny/extended UART variants */
    #define USART_RX_vect_name    USARTE_RX_vect
    #define USART_UDRE_vect_name  USARTE_UDRE_vect
#else
    #error "Unsupported AVR MCU for UART0"
#endif


ISR(USART_RX_vect_name)
{
    uint8_t byte = UDR0; /* always read UDR0 to clear the RXC flag */
    if (!rb_push(&rx_buffer, byte))
        rx_buffer.overflow_flag = 1; /* buffer full — byte dropped, notify poll */
}

ISR(USART_UDRE_vect_name)
{
    uint8_t data;
    if (rb_pop(&tx_buffer, &data))
    {
        UDR0 = data; /* Next byte */
    }
    else
    {
        UCSR0B &= ~(1 << UDRIE0); /* No data, disable interrupt */
    }
}

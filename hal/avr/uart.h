#ifndef UART_H
#define UART_H

#include <stdint.h>

/* AVR-private UART driver */
void uart_init(uint32_t baudrate);
uint8_t uart_putc(uint8_t data);
uint8_t uart_getc_nonblocking(uint8_t *data);

#endif // UART_H

#ifndef UART_H
#define UART_H

#include <stdint.h>
#include "mcu_mdt_config.h"

typedef struct {
    uint8_t buf[MDT_RX_BUFFER_SIZE];
    volatile uint8_t head;
    volatile uint8_t tail;
} ring_buffer_t;

/* AVR-private UART driver */
void uart_init(uint32_t baudrate);
void uart_putc(uint8_t data);
uint8_t uart_getc_nonblocking(uint8_t *data);

#endif // UART_H

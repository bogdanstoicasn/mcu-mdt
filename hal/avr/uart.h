#ifndef UART_H
#define UART_H

#include <stdint.h>
#include "../../inc/mcu_mdt_config.h"

/* UART initialization and low-level functions */
void uart_init(uint32_t baudrate);
void uart_putc(uint8_t data);
uint8_t uart_getc(void);
uint8_t uart_data_available(void);

#endif // UART_H
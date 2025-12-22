#ifndef HAL_AVR_H
#define HAL_AVR_H

#include <stdint.h>

/* AVR-private UART driver */
void hal_uart_init(void);
void hal_uart_tx(uint8_t byte);
int  hal_uart_rx(uint8_t *byte);

#endif /* HAL_AVR_H */

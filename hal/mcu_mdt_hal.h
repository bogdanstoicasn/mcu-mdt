#ifndef MCU_MDT_HAL_H
#define MCU_MDT_HAL_H

#include <stdint.h>

/* ===== UART HAL ===== */

/**
 * @brief Initialize UART peripheral
 */
void hal_uart_init(void);

/**
 * @brief Send one byte (blocking is allowed)
 */
void hal_uart_tx(uint8_t byte);

/**
 * @brief Try to read one byte (non-blocking)
 * @param byte Pointer where received byte is stored
 * @return 1 if byte was read, 0 if no data available
 */
int hal_uart_rx(uint8_t *byte);

#endif /* MCU_MDT_HAL_H */

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

/**
 * @brief Read memory from the target device
 * @param mem_zone Memory zone to read from (SRAM, FLASH, EEPROM)
 * @param address Address to read from
 * @param buffer Buffer where read data will be stored
 * @param length Number of bytes to read
 * @return 1 on success, 0 on failure
 */
uint8_t hal_read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length);

/**
 * @brief read register
 * @param address Address to read from
 * @param buffer Buffer where read data will be stored
 * @return 1 on success, 0 on failure
 */
uint32_t hal_read_register(uint32_t address, uint8_t *buffer);

#endif /* MCU_MDT_HAL_H */

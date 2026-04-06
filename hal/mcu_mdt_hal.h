#ifndef MCU_MDT_HAL_H
#define MCU_MDT_HAL_H

#include <stdint.h>

/* ===== UART HAL ===== */

/**
 * @brief Initialize UART peripheral
 */
void hal_uart_init(void);

/**
 * @brief Enqueue a buffer for async transmission via the TX ring buffer.
 *        Returns the number of bytes actually enqueued; may be less than
 *        len if the ring buffer is full.  The ISR drains the buffer in
 *        the background — the caller does not block.
 * @param buf  Pointer to data to send
 * @param len  Number of bytes to send
 * @return     Number of bytes enqueued (0..len)
 */
uint8_t hal_uart_tx_buf(const uint8_t *buf, uint8_t len);

/**
 * @brief Check if the RX ring buffer dropped a byte since the last call.
 *        Returns 1 and clears the flag if an overflow occurred, 0 otherwise.
 *        Called from mcu_mdt_poll() to surface dropped bytes as an event.
 */
uint8_t hal_uart_rx_overflow(void);

/**
 * @brief Try to read one byte (non-blocking)
 * @param byte Pointer where received byte is stored
 * @return 1 if byte was read, 0 if no data available
 */
uint8_t hal_uart_rx(uint8_t *byte);

/**
 * @brief Check if the TX ring buffer has space for at least one byte.
 * @return 1 if ready, 0 if not
 */
uint8_t hal_uart_tx_ready(void);

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
 * @brief Read a register from the target device
 * @param address Address of the register to read
 * @param buffer Buffer where read data will be stored (1 byte)
 * @return 1 on success, 0 on failure
 */
uint8_t hal_read_register(uint32_t address, uint8_t *buffer);

/**
 * @brief Write memory to the target device
 * @param mem_zone Memory zone to write to (SRAM, EEPROM)
 * @param address Address to write to
 * @param buffer Buffer containing data to write
 * @param length Number of bytes to write
 * @return 1 on success, 0 on failure
 */
uint8_t hal_write_memory(uint8_t mem_zone, uint32_t address, const uint8_t *buffer, uint16_t length);

/**
 * @brief Write a register on the target device
 * @param address Address of the register to write
 * @param buffer Buffer containing data to write (1 byte)
 * @return 1 on success, 0 on failure
 */
uint8_t hal_write_register(uint32_t address, const uint8_t *buffer);

#endif /* MCU_MDT_HAL_H */

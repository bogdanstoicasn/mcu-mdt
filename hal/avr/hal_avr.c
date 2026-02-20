#include "mcu_mdt_hal.h"
#include "mcu_mdt_config.h"
#include "uart.h"
#include "commands.h"

void hal_uart_init(void)
{
    uart_init(MDT_UART_BAUDRATE);
}

void hal_uart_tx(uint8_t byte)
{
    uart_putc(byte);
}

int hal_uart_rx(uint8_t *byte)
{
    return uart_getc_nonblocking(byte);
}

uint8_t hal_read_memory(uint8_t mem_zone, uint32_t address, uint8_t *buffer, uint16_t length)
{
    return read_memory(mem_zone, address, buffer, length);
}

uint32_t hal_read_register(uint32_t address, uint8_t *buffer)
{
    return read_register(address, buffer);
}

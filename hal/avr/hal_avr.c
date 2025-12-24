#include "mcu_mdt_hal.h"
#include "mcu_mdt_config.h"
#include "uart.h"

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

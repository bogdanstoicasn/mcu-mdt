#include "uart.h"
#include "ring_buffer.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0 };

void uart_init(uint32_t baudrate)
{
    
}
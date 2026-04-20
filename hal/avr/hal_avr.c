/*
 * hal_avr.c — AVR HAL implementation
 *
 * Architecture notes:
 *   - UART: ring-buffer driven, ISR-based TX, polling RX (no IDLE interrupt on AVR).
 *   - Memory: SRAM/FLASH (pgmspace) / EEPROM zones, byte-granular access.
 *   - Registers: treated as SRAM byte reads/writes (I/O register space is memory-mapped).
 *
 * The HAL interface (mcu_mdt_hal.h) is implemented directly here.
 * There are NO intermediate read_memory / write_memory wrappers — the hal_*
 * functions are the only entry points, keeping the call graph flat.
 */

#include "mcu_mdt_hal.h"
#include "ring_buffer.h"

#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <avr/eeprom.h>

/*  Ring buffers */
static ring_buffer_t rx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };


/* UART vector portability — single/multi-UART AVR families */

#if defined(USART_RX_vect)        /* ATmega328P, ATmega168, etc.  */
    #define USART_RX_vect_name    USART_RX_vect
    #define USART_UDRE_vect_name  USART_UDRE_vect
#elif defined(USART0_RX_vect)     /* ATmega2560, ATmega1280, etc. */
    #define USART_RX_vect_name    USART0_RX_vect
    #define USART_UDRE_vect_name  USART0_UDRE_vect
#elif defined(USARTE_RX_vect)     /* ATtiny/extended UART variants */
    #define USART_RX_vect_name    USARTE_RX_vect
    #define USART_UDRE_vect_name  USARTE_UDRE_vect
#else
    #error "Unsupported AVR MCU: no known UART0 vector"
#endif


/* ISRs */

ISR(USART_RX_vect_name)
{
    uint8_t byte = UDR0; /* always read to clear RXC flag */
    if (!rb_push(&rx_buffer, byte))
        rx_buffer.overflow_flag = 1;
}

ISR(USART_UDRE_vect_name)
{
    uint8_t data;
    if (rb_pop(&tx_buffer, &data))
        UDR0 = data;
    else
        UCSR0B &= ~(1 << UDRIE0); /* TX queue empty, disable interrupt */
}


/* HAL: UART */

void hal_uart_init(void)
{
    uint16_t ubrr = (F_CPU / (16UL * MDT_UART_BAUDRATE)) - 1;

    UBRR0H = (uint8_t)(ubrr >> 8);
    UBRR0L = (uint8_t)ubrr;

    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);

    sei();
}

uint8_t hal_uart_tx_buf(const uint8_t *buf, uint8_t len)
{
    uint8_t sent = 0;
    while (sent < len)
    {
        if (!rb_push(&tx_buffer, buf[sent]))
            break;
        sent++;
    }
    if (sent)
        UCSR0B |= (1 << UDRIE0); /* enable TX interrupt to drain the queue */
    return sent;
}

uint8_t hal_uart_rx(uint8_t *byte)
{
    return rb_pop(&rx_buffer, byte);
}

uint8_t hal_uart_tx_ready(void)
{
    return !rb_is_full(&tx_buffer);
}

uint8_t hal_uart_tx_empty(void)
{
    return rb_is_empty(&tx_buffer);
}

uint8_t hal_uart_rx_overflow(void)
{
    if (rx_buffer.overflow_flag)
    {
        rx_buffer.overflow_flag = 0;
        return 1;
    }
    return 0;
}


/* HAL: Memory access */

uint8_t hal_read_memory(uint8_t mem_zone, uint32_t address,
                        uint8_t *buffer, uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    uintptr_t addr = (uintptr_t)address;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
            for (uint16_t i = 0; i < length; i++)
                buffer[i] = *((volatile uint8_t *)(addr + i));
            return 1;

        case MDT_MEM_ZONE_FLASH:
            for (uint16_t i = 0; i < length; i++)
                buffer[i] = pgm_read_byte((const void *)(addr + i));
            return 1;

        case MDT_MEM_ZONE_EEPROM:
            for (uint16_t i = 0; i < length; i++)
                buffer[i] = eeprom_read_byte((const uint8_t *)(addr + i));
            return 1;

        default:
            return 0;
    }
}

uint8_t hal_write_memory(uint8_t mem_zone, uint32_t address,
                         const uint8_t *buffer, uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
            for (uint16_t i = 0; i < length; i++)
                *((volatile uint8_t *)(uintptr_t)(address + i)) = buffer[i];
            return 1;

        case MDT_MEM_ZONE_EEPROM:
            eeprom_write_block(buffer, (void *)(uintptr_t)address, length);
            return 1;

        default:
            return 0; /* FLASH writes not supported on AVR via this interface */
    }
}

uint8_t hal_read_register(uint32_t address, uint8_t *buffer)
{
    /* Registers are in SRAM address space; single-byte read. */
    return hal_read_memory(MDT_MEM_ZONE_SRAM, address, buffer, 1);
}

uint8_t hal_write_register(uint32_t address, const uint8_t *buffer)
{
    return hal_write_memory(MDT_MEM_ZONE_SRAM, address, buffer, 1);
}

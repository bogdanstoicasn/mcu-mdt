#include "uart.h"
#include "ring_buffer.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0 };

void uart_init(uint32_t baudrate)
{
    RCC->apb2enr |= RCC_APB2ENR_USART1EN;
    RCC->ahbenr |= RCC_AHBENR_GPIOAEN;

    /* PA9 config (pin 9 = CRH bits 4..7) (i think?) */

    /* // PA10 config (pin 10 = CRH bits 8..11) (i think)*/

    /* BRR = CLOCk / baud */
    USART1->brr = (uint32_t)(F_CPU / baudrate);

     /* Enable USART, TX, RX and RX interrupt */
    USART1->cr1 |= USART_CR1_UE | USART_CR1_RE | USART_CR1_TE;

    /* Enable NVIC for USART1 */
    NVIC_ISER[USART1_IRQ / 32] = 1U << (USART1_IRQ % 32);
}

uint8_t uart_putc(uint8_t data)
{
    if (rb_is_full(&tx_buffer))
    {
        return 0;
    }

    rb_push(&tx_buffer, data);

    USART1->cr1 |= USART_CR1_TXEIE;

    return 1;
}

uint8_t uart_getc_nonblocking(uint8_t *data)
{
    return rb_pop(&rx_buffer, data);
}

uint8_t uart_ready(void)
{
    return !rb_is_full(&tx_buffer);
}

uint8_t uart_rx_overflow(void)
{
    if (rx_buffer.overflow_flag)
    {
        rx_buffer.overflow_flag = 0;
        return 1;
    }
    return 0;
}

void USART1_IRQHandler(void)
{
    uint32_t sr = USART1->sr;

    /* RX data received */
    if (sr & USART_SR_RXNE)
    {
        uint8_t data = (uint8_t)USART1->dr;
        if (!rb_push(&rx_buffer, data))
            rx_buffer.overflow_flag = 1;
    }

    if (sr & USART_SR_TXE)
    {
        uint8_t data;
        if (rb_pop(&tx_buffer, &data))
            USART1->dr = data;
        else
            USART1->cr1 &= ~USART_CR1_TXEIE; /* disable TX interrupt */
    }

    /* Clear overrun error */
    if (sr & USART_SR_ORE)
    {
        volatile uint32_t tmp = USART1->dr;
        (void)tmp;
    }
}

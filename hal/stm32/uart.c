#include "uart.h"
#include "ring_buffer.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0 };

static ring_buffer_t tx_buffer = { .head = 0, .tail = 0 };

/* UART */

void uart_init(uint32_t baudrate)
{
    RCC->ahbenr |= RCC_AHBENR_GPIOAEN; // Enable GPIOA clock
    RCC->apb2enr |= RCC_APB2ENR_USART1EN; // Enable USART1 clock

    /* Configure PA9 (TX) and PA10 (RX) as alternate function */
    GPIOA->moder &= ~(3<<(9*2));
    GPIOA->moder |=  (2<<(9*2));

    GPIOA->moder &= ~(3<<(10*2));
    GPIOA->moder |=  (2<<(10*2));

    /* AF1 */
    GPIOA->afrh &= ~(0xF<<4);
    GPIOA->afrh |=  (1<<4);

    GPIOA->afrh &= ~(0xF<<8);
    GPIOA->afrh |=  (1<<8);

    /* Configure USART1 */
    USART1->brr = 48000000 / baudrate; // Assuming PCLK2 is 48 MHz

    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE | USART_CR1_RXNEIE; // Enable USART, RX, TX and RX interrupt

    /* Enable USART1 interrupt in NVIC */
    NVIC_ISER[USART1_IRQ/32] = 1 << (USART1_IRQ % 32);
}

uint8_t uart_putc(uint8_t data)
{
    if (rb_is_full(&tx_buffer))
    {
        return 0;
    }
    rb_push(&tx_buffer, data);

    USART1->cr1 |= USART_CR1_TXEIE; // Enable TXE interrupt
    return 1;
}

uint8_t uart_getc_nonblocking(uint8_t *data)
{
    return rb_pop(&rx_buffer, data);
}

uint8_t uart_ready()
{
    return !rb_is_full(&tx_buffer);
}

/* Interrupt Service Routines */
void USART1_IRQHandler(void)
{
    if (USART1->isr & USART_ISR_RXNE)
    {
        uint8_t data = USART1->rdr; // Read received byte
        rb_push(&rx_buffer, data); // Push to RX buffer
    }

    if (USART1->isr & USART_ISR_TXE)
    {
        uint8_t data;
        if (rb_pop(&tx_buffer, &data))
        {
            USART1->tdr = data; // Write byte to transmit
        }
        else
        {
            USART1->cr1 &= ~USART_CR1_TXEIE; // Disable TXE interrupt if no more data
        }
    }
}
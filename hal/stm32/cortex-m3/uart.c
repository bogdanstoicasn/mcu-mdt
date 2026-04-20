#include "uart.h"
#include "ring_buffer.h"

static ring_buffer_t rx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };

#if MDT_FEATURE_UART_IDLE
/* Set by IDLE ISR, consumed by PendSV_Handler */
static volatile uint8_t pending_flag = 0;

/* Registered by HAL — called from PendSV_Handler to process received packet */
static void (*idle_callback)(void) = 0;
#endif

void uart_init(uint32_t baudrate)
{
    RCC->apb2enr |= RCC_APB2ENR_IOPAEN
                 |  RCC_APB2ENR_USART1EN
                 |  RCC_APB2ENR_AFIOEN;

    GPIOA->crh &= ~(0xFU << 4);   /* clear PA9 field */
    GPIOA->crh |=  (0xBU << 4);   /* AF push-pull, 50 MHz */

    GPIOA->crh &= ~(0xFU << 8);   /* clear PA10 field */
    GPIOA->crh |=  (0x4U << 8);   /* floating input */

    USART1->brr = (uint32_t)(F_CPU / baudrate);

#if MDT_FEATURE_UART_IDLE
    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE | USART_CR1_RXNEIE | USART_CR1_IDLEIE;
#else
    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE | USART_CR1_RXNEIE;
#endif

    /* Enable NVIC for USART1 */
    NVIC_ISER[USART1_IRQ / 32] = 1U << (USART1_IRQ % 32);

#if MDT_FEATURE_UART_IDLE
    /* PendSV must be the lowest-priority exception so it runs after all IRQs.
     * Writing 0xFF gives the lowest possible priority (highest numeric value). */
    SCB_SHP3 |= PENDSV_PRI_LOWEST;
#endif
}

uint8_t uart_putc(uint8_t data)
{
    if (rb_is_full(&tx_buffer))
        return 0;

    rb_push(&tx_buffer, data);
    USART1->cr1 |= USART_CR1_TXEIE; /* kick the TX interrupt */
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

uint8_t uart_tx_empty(void)
{
    return rb_is_empty(&tx_buffer);
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

#if MDT_FEATURE_UART_IDLE
void uart_set_idle_callback(void (*cb)(void))
{
    idle_callback = cb;
}

/* PendSV_Handler — runs at lowest priority, after all IRQs have completed.
 * Consumes the pending_flag set by the IDLE ISR and calls the registered
 * callback (mdt_process_pending) to drain the ring buffer and dispatch. */
void PendSV_Handler(void)
{
    if (pending_flag)
    {
        pending_flag = 0;
        if (idle_callback)
            idle_callback();
    }
}
#endif

void USART1_IRQHandler(void)
{
    uint32_t sr = USART1->sr;

    if (sr & USART_SR_RXNE)
    {
        uint8_t data = (uint8_t)USART1->dr;
        if (!rb_push(&rx_buffer, data))
            rx_buffer.overflow_flag = 1;
    }

#if MDT_FEATURE_UART_IDLE
    if (sr & USART_SR_IDLE)
    {
        volatile uint32_t tmp;

        tmp = USART1->sr;
        tmp = USART1->dr;
        (void)tmp;

        pending_flag = 1;
        SCB_ICSR     = SCB_PENDSV_SET;
    }
#endif

    if (sr & USART_SR_TXE)
    {
        uint8_t data;
        if (rb_pop(&tx_buffer, &data))
            USART1->dr = data;
        else
            USART1->cr1 &= ~USART_CR1_TXEIE; /* Disable TX interrupt */
    }

    /* Clear overrun error */
    if ((sr & USART_SR_ORE) && !(sr & USART_SR_RXNE))
    {
        volatile uint32_t tmp = USART1->dr;
        (void)tmp;
    }
}

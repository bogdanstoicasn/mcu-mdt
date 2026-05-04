/*
 * hal_stm.c — STM32F103 (Cortex-M3) HAL implementation
 *
 * Architecture notes:
 *   - UART: ring-buffer driven, fully interrupt-based (RX, TX, IDLE).
 *   - IDLE interrupt → PendSV (lowest priority) → registered idle callback.
 *     IDLE flag is cleared by reading SR then DR (F1 series errata sequence).
 *   - Memory: SRAM and FLASH share the same linear address space — reads are
 *     plain pointer dereferences. FLASH write is not implemented on this target.
 *   - Registers are memory-mapped and 32-bit wide; hal_read/write_register
 *     uses a 4-byte SRAM access.
 *
 * The HAL interface (mcu_mdt_hal.h) is implemented directly here.
 * There are NO intermediate read_memory / write_memory wrappers — the hal_*
 * functions are the only entry points, keeping the call graph flat.
 */

#include "mcu_mdt_hal.h"
#include "ring_buffer.h"
#include "uart.h"
#include "commands.h"

/*  Ring buffers */
static ring_buffer_t rx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };

/* IDLE callback */
#if MDT_FEATURE_UART_IDLE
static volatile uint8_t pending_flag = 0;
static void (*idle_callback)(void)   = 0;

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


/* USART1 ISR */

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
        /* Reading SR then DR clears the IDLE flag on F1 series */
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
            USART1->cr1 &= ~USART_CR1_TXEIE;
    }

    /* Clear overrun error — must read DR to dismiss ORE when RXNE is not also set */
    if ((sr & USART_SR_ORE) && !(sr & USART_SR_RXNE))
    {
        volatile uint32_t tmp = USART1->dr;
        (void)tmp;
    }
}


/* HAL: UART*/

void hal_uart_init(void)
{
    RCC->apb2enr |= RCC_APB2ENR_IOPAEN
                 |  RCC_APB2ENR_USART1EN
                 |  RCC_APB2ENR_AFIOEN;

    GPIOA->crh &= ~(0xFU << 4);  /* PA9  TX: AF push-pull, 50 MHz */
    GPIOA->crh |=  (0xBU << 4);
    GPIOA->crh &= ~(0xFU << 8);  /* PA10 RX: floating input */
    GPIOA->crh |=  (0x4U << 8);

    USART1->brr = (uint32_t)(F_CPU / MDT_UART_BAUDRATE);

#if MDT_FEATURE_UART_IDLE
    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE
                | USART_CR1_RXNEIE | USART_CR1_IDLEIE;
    /* PendSV must be the lowest-priority exception so it runs after all IRQs.
     * Writing 0xFF gives the lowest possible priority (highest numeric value). */
    SCB_SHP3   |= PENDSV_PRI_LOWEST;
#else
    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE
                | USART_CR1_RXNEIE;
#endif

    NVIC_ISER[USART1_IRQ / 32] = 1U << (USART1_IRQ % 32);
}

uint8_t hal_uart_tx_buf(const uint8_t *buf, uint8_t len)
{
    uint8_t sent = 0;
    while (sent < len)
    {
        if (rb_is_full(&tx_buffer))
            break;
        rb_push(&tx_buffer, buf[sent++]);
        USART1->cr1 |= USART_CR1_TXEIE;
    }
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

void hal_uart_set_idle_callback(void (*cb)(void))
{
#if MDT_FEATURE_UART_IDLE
    idle_callback = cb;
#else
    (void)cb;
#endif
}

void hal_reset(void)
{
    while (!rb_is_empty(&tx_buffer));
 
    *((volatile uint32_t *)0xE000ED0C) = 0x05FA0004;
 
    while (1);
}


/* Flash helpers — private to this file */
static inline void flash_unlock(void)
{
    if (FLASH->cr & FLASH_CR_LOCK)
    {
        FLASH->keyr = FLASH_KEY1;
        FLASH->keyr = FLASH_KEY2;
    }
}

static inline void flash_lock(void)
{
    FLASH->cr |= FLASH_CR_LOCK;
}

static inline void flash_wait_busy(void)
{
    while (FLASH->sr & FLASH_SR_BSY);
}

static inline void flash_clear_flags(void)
{
    FLASH->sr = FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPTERR;
}

static uint8_t flash_is_erased(uint32_t address, uint16_t length)
{
    uint16_t len_hw = (length + 1U) & ~1U;   /* round up to even */
    for (uint16_t i = 0; i < len_hw; i += 2)
    {
        if (*((volatile uint16_t *)(uintptr_t)(address + i)) != 0xFFFFU)
            return 0;
    }
    return 1;
}

static uint8_t flash_write_halfword(uint32_t address, uint16_t data)
{
    flash_wait_busy();
    flash_clear_flags();

    FLASH->cr |= FLASH_CR_PG;

    *((volatile uint16_t *)(uintptr_t)address) = data;

    flash_wait_busy();

    uint8_t ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  =  FLASH_SR_EOP;    /* clear EOP  (w1c) */
    FLASH->cr &= ~FLASH_CR_PG;     /* exit programming mode */

    return ok;
}

static uint8_t flash_erase_page(uint32_t address)
{
    flash_wait_busy();
    flash_clear_flags();

    FLASH->cr |= FLASH_CR_PER;     /* select page-erase mode */
    FLASH->ar  = address;          /* point at the page      */
    FLASH->cr |= FLASH_CR_STRT;    /* start the erase        */

    flash_wait_busy();

    uint8_t ok  = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr   =  FLASH_SR_EOP;
    FLASH->cr  &= ~FLASH_CR_PER;   /* exit page-erase mode   */

    return ok;
}


/* HAL: Memory */

uint8_t hal_read_memory(uint8_t mem_zone, uint32_t address,
                        uint8_t *buffer, uint16_t length)
{
    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
        case MDT_MEM_ZONE_FLASH:
            for (uint16_t i = 0; i < length; i++)
                buffer[i] = *((volatile uint8_t *)(uintptr_t)(address + i));
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

        default:
            return 0; /* TODO: FLASH write not implemented on M3 */
    }
}

uint8_t hal_read_register(uint32_t address, uint8_t *buffer)
{
    if (!buffer || (address & 0x3))
        return 0;

    uint32_t val = *((volatile uint32_t *)(uintptr_t)address);

    buffer[0] = (uint8_t)(val);
    buffer[1] = (uint8_t)(val >> 8);
    buffer[2] = (uint8_t)(val >> 16);
    buffer[3] = (uint8_t)(val >> 24);

    return 1;
}

uint8_t hal_write_register(uint32_t address, const uint8_t *buffer)
{
    if (!buffer || (address & 0x3))
        return 0;

    uint32_t val = (uint32_t)buffer[0]
                 | ((uint32_t)buffer[1] << 8)
                 | ((uint32_t)buffer[2] << 16)
                 | ((uint32_t)buffer[3] << 24);

    *((volatile uint32_t *)(uintptr_t)address) = val;

    return 1;
}

/*
 * hal_stm.c — STM32F030 (Cortex-M0) HAL implementation
 *
 * Architecture notes:
 *   - UART: ring-buffer driven, fully interrupt-based (RX, TX, IDLE).
 *   - IDLE interrupt → PendSV (lowest priority) → registered idle callback.
 *   - Memory: SRAM and FLASH share the same linear address space — reads are
 *     plain pointer dereferences. FLASH writes use half-word (16-bit)
 *     programming only; Cortex-M0 hard-faults on byte or word-wide writes.
 *   - Registers are memory-mapped and 32-bit wide; hal_read/write_register
 *     uses a 4-byte SRAM access.
 *
 * The HAL interface (mcu_mdt_hal.h) is implemented directly here.
 * There are NO intermediate read_memory / write_memory wrappers — the hal_*
 * functions are the only entry points, keeping the call graph flat.
 * Flash helpers (unlock, lock, write_halfword, etc.) are static to this file;
 * they are an implementation detail of hal_write_memory, not a public interface.
 */

#include "mcu_mdt_hal.h"
#include "ring_buffer.h"
#include "uart.h"
#include "commands.h"

/* Ring buffers */
static ring_buffer_t rx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };
static ring_buffer_t tx_buffer = { .head = 0, .tail = 0, .overflow_flag = 0 };


/* IDLE callback */

#if MDT_FEATURE_UART_IDLE
static volatile uint8_t pending_flag  = 0;
static void (*idle_callback)(void)    = 0;

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
    uint32_t isr = USART1->isr;

    if (isr & USART_ISR_ORE)
        USART1->icr = USART_ICR_ORECF;

    if (isr & USART_ISR_RXNE)
    {
        uint8_t data = (uint8_t)USART1->rdr;
        if (!rb_push(&rx_buffer, data))
            rx_buffer.overflow_flag = 1;
    }

#if MDT_FEATURE_UART_IDLE
    if (isr & USART_ISR_IDLE)
    {
        USART1->icr  = USART_ICR_IDLECF;
        pending_flag = 1;
        SCB_ICSR     = SCB_PENDSV_SET;
    }
#endif

    if (isr & USART_ISR_TXE)
    {
        uint8_t data;
        if (rb_pop(&tx_buffer, &data))
            USART1->tdr = data;
        else
            USART1->cr1 &= ~USART_CR1_TXEIE;
    }
}


/* HAL: UART */

void hal_uart_init(void)
{
    RCC->ahbenr  |= RCC_AHBENR_GPIOAEN;
    RCC->apb2enr |= RCC_APB2ENR_USART1EN;

    GPIOA->moder &= ~(GPIO_MODER_MASK << (USART1_TX_PIN * 2));
    GPIOA->moder |=  (GPIO_MODER_AF   << (USART1_TX_PIN * 2));
    GPIOA->moder &= ~(GPIO_MODER_MASK << (USART1_RX_PIN * 2));
    GPIOA->moder |=  (GPIO_MODER_AF   << (USART1_RX_PIN * 2));

    GPIOA->afrh &= ~(0xFU << USART1_TX_AFRH_POS);
    GPIOA->afrh |=  (GPIO_AF1 << USART1_TX_AFRH_POS);
    GPIOA->afrh &= ~(0xFU << USART1_RX_AFRH_POS);
    GPIOA->afrh |=  (GPIO_AF1 << USART1_RX_AFRH_POS);

    USART1->brr = (uint32_t)(F_CPU / MDT_UART_BAUDRATE);

#if MDT_FEATURE_UART_IDLE
    USART1->cr1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE
                | USART_CR1_RXNEIE | USART_CR1_IDLEIE;
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
    /* Drain TX ring buffer so the ACK packet is fully sent before reset */
    while (!rb_is_empty(&tx_buffer));
 
    /* Request system reset via AIRCR — works on Cortex-M0 and M3/M4 */
    *((volatile uint32_t *)0xE000ED0C) = 0x05FA0004;
 
    while (1); /* unreachable — suppress noreturn warning */
}


/* Flash helpers — private to this file */

static inline void flash_unlock(void)
{
    /* RM0360 §3.1: HSI must be on for all flash program/erase operations.
     * If the system is running from HSE or PLL-from-HSE with HSI off, every
     * flash operation hangs or fails without this. The wait is ~1 µs worst-
     * case; if HSI is already running (HSIRDY=1) it returns immediately. */
    RCC->cr |= (1U << 0);             /* HSION */
    while (!(RCC->cr & (1U << 1)));   /* wait HSIRDY */

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
    FLASH->sr = FLASH_SR_PGERR | FLASH_SR_WRPRTERR | FLASH_SR_EOP;
}

static uint8_t flash_is_erased(uint32_t address, uint16_t length)
{
    for (uint16_t i = 0; i < length; i += 2)
    {
        if (*((volatile uint16_t *)(uintptr_t)(address + i)) != 0xFFFF)
            return 0;
    }
    return 1;
}

static uint8_t flash_write_halfword(uint32_t address, uint16_t data)
{
    flash_wait_busy();
    flash_clear_flags();

    FLASH->cr |= FLASH_CR_PG;

    /* Half-word write, other widths cause hard fault on Cortex-M0 */
    *((volatile uint16_t *)(uintptr_t)address) = data;

    flash_wait_busy();

    uint8_t ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  = FLASH_SR_EOP;
    FLASH->cr &= ~FLASH_CR_PG;

    return ok;
}

static uint8_t flash_write_word(uint32_t address, uint32_t data)
{
    if (address & 0x1)   /* halfword alignment only — word alignment is not required by the flash controller */
        return 0;

    flash_unlock();

    uint8_t ok = flash_write_halfword(address,     (uint16_t)(data & 0xFFFF));
    if (ok)
        ok     = flash_write_halfword(address + 2, (uint16_t)(data >> 16));

    flash_lock();
    return ok;
}

static uint8_t flash_erase_page(uint32_t address)
{
    uint32_t page_base = address & ~(FLASH_PAGE_SIZE - 1UL);

    flash_unlock();

    flash_wait_busy();
    flash_clear_flags();

    FLASH->cr |= FLASH_CR_PER;
    FLASH->ar  = page_base;
    FLASH->cr |= FLASH_CR_STRT;

    flash_wait_busy();

    uint8_t ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  = FLASH_SR_EOP;
    FLASH->cr &= ~FLASH_CR_PER;

    flash_lock();
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
    /* ERASE ignores buffer and length entirely — handle it before the
     * null/length guard so callers are not forced to pass dummy data. */
    if (mem_zone == MDT_MEM_ZONE_ERASE)
        return flash_erase_page(address);

    if (!buffer || length == 0)
        return 0;

    switch (mem_zone)
    {
        case MDT_MEM_ZONE_SRAM:
            for (uint16_t i = 0; i < length; i++)
                *((volatile uint8_t *)(uintptr_t)(address + i)) = buffer[i];
            return 1;

        case MDT_MEM_ZONE_FLASH:
        {
            if (address & 0x1)
                return 0;

            if (!flash_is_erased(address, length))
                return 0;

            if (length <= 2)
            {
                uint16_t hw;
                if (length == 2)
                    hw = (uint16_t)buffer[0] | ((uint16_t)buffer[1] << 8);
                else
                    hw = (uint16_t)buffer[0] | 0xFF00; /* keep upper byte erased */

                flash_unlock();
                uint8_t ok = flash_write_halfword(address, hw);
                flash_lock();
                return ok;
            }
            else
            {
                uint32_t word = 0xFFFFFFFF;
                for (uint16_t i = 0; i < length && i < 4; i++)
                    word = (word & ~(0xFFUL << (i * 8))) | ((uint32_t)buffer[i] << (i * 8));

                return flash_write_word(address, word);
            }
        }

        case MDT_MEM_ZONE_ERASE:
            /* Unreachable — handled above before the null/length guard.
             * Kept here so the compiler does not warn on an unhandled enum value. */
            return flash_erase_page(address);

        default:
            return 0;
    }
}

uint8_t hal_read_register(uint32_t address, uint8_t *buffer)
{
    if (!buffer || (address & 0x3))   // must be word-aligned
        return 0;

    uint32_t val = *((volatile uint32_t *)(uintptr_t)address);

    // Store little-endian into buffer
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

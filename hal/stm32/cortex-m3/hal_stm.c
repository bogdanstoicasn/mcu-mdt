/*
 * hal_stm.c — STM32F103 (Cortex-M3) HAL implementation
 *
 * Architecture notes:
 *   - UART: ring-buffer driven, fully interrupt-based (RX, TX, IDLE).
 *   - IDLE interrupt PendSV (lowest priority) registered idle callback.
 *     IDLE flag is cleared by reading SR then DR (F1 series errata sequence).
 *   - Memory: SRAM and FLASH share the same linear address space — reads are
 *     plain pointer dereferences. FLASH writes use half-word (16-bit)
 *     programming only (RM0008 §3.3.3); byte or word writes are not supported
 *     by the flash controller. XL-density parts (F103xF/G) have dual flash
 *     banks; addresses >= 0x0808 0000 use the bank-2 control registers.
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

    uint32_t baud_div = (F_CPU + (MDT_UART_BAUDRATE/2U)) / MDT_UART_BAUDRATE;
    USART1->brr = ((baud_div / 16U) << 4) | ((baud_div % 16U) & 0xFU);

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

    NVIC_ISER[USART1_IRQ / 32] |= 1U << (USART1_IRQ % 32);
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
    /* Flush the ACK before reset. The TX buffer may be empty while the last
     * byte is still shifting out, so wait for TC (transmission complete) too.
     * Waits are bounded to avoid blocking the reset. */
    uint32_t timeout = 1000000UL;
    while (!rb_is_empty(&tx_buffer))
    {
        if (--timeout == 0)
            break;
    }
    timeout = 1000000UL;
    while (!(USART1->sr & USART_SR_TC))
    {
        if (--timeout == 0)
            break;
    }
 
    *((volatile uint32_t *)0xE000ED0C) = 0x05FA0004;
 
    while (1);
}


static inline void flash_ensure_hsi(void)
{
    /* Bounded wait: HSI starts in a few us; if it somehow never readies,
     * proceed anyway -- the flash op will then fail EOP and NACK cleanly
     * instead of hanging the debug link here. */
    uint32_t timeout = 100000UL;
    RCC->cr |= (1U << 0);             /* HSION  */
    while (!(RCC->cr & (1U << 1)))    /* HSIRDY */
    {
        if (--timeout == 0)
            break;
    }
}

static inline void flash_unlock(void)
{
    flash_ensure_hsi();
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

/* Bounded BSY wait. Real flash operations stall the CPU, so the timeout
 * only catches a stuck BSY. Returns 1 on completion, 0 on timeout. */
#define FLASH_TIMEOUT_LOOPS  2000000UL

static uint8_t flash_wait_busy(void)
{
    uint32_t timeout = FLASH_TIMEOUT_LOOPS;
    while (FLASH->sr & FLASH_SR_BSY)
    {
        if (--timeout == 0)
            return 0;
    }
    return 1;
}

static inline void flash_clear_flags(void)
{
    FLASH->sr = FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPRTERR;
}

/* XL-density bank 2 helpers
 * F103xF and F103xG have 1 MB of flash split into two independent 512 KB
 * banks. Bank 2 (0x0808 0000 – 0x080F FFFF) has its own control registers
 * (FLASH_CR2/SR2/AR2/KEYR2). Both banks share the same bit definitions. */
#ifdef FLASH_XL_DENSITY

static inline void flash_unlock2(void)
{
    flash_ensure_hsi();
    if (FLASH_CR2 & FLASH_CR_LOCK)
    {
        FLASH_KEYR2 = FLASH_KEY1;
        FLASH_KEYR2 = FLASH_KEY2;
    }
}

static inline void flash_lock2(void)
{
    FLASH_CR2 |= FLASH_CR_LOCK;
}

static uint8_t flash_wait_busy2(void)
{
    uint32_t timeout = FLASH_TIMEOUT_LOOPS;
    while (FLASH_SR2 & FLASH_SR_BSY)
    {
        if (--timeout == 0)
            return 0;
    }
    return 1;
}

static inline void flash_clear_flags2(void)
{
    FLASH_SR2 = FLASH_SR_EOP | FLASH_SR_PGERR | FLASH_SR_WRPRTERR;
}

#endif /* FLASH_XL_DENSITY */

/* Verify a whole page reads back erased after an erase operation. */
static uint8_t flash_page_blank(uint32_t page_base)
{
    for (uint32_t i = 0; i < FLASH_PAGE_SIZE; i += 2)
    {
        if (*((volatile uint16_t *)(uintptr_t)(page_base + i)) != 0xFFFFU)
            return 0;
    }
    return 1;
}

static uint8_t flash_is_erased(uint32_t address, uint16_t length)
{
    /* Round up to even — writes always touch a full halfword, so both bytes
     * of the target halfword must be 0xFF even for a 1-byte write. */
    uint16_t len_hw = (length + 1U) & ~1U;
    for (uint16_t i = 0; i < len_hw; i += 2)
    {
        if (*((volatile uint16_t *)(uintptr_t)(address + i)) != 0xFFFFU)
            return 0;
    }
    return 1;
}

static uint8_t flash_write_halfword(uint32_t address, uint16_t data)
{
    /* Bank 2 path — XL-density only */
#ifdef FLASH_XL_DENSITY
    if (address >= FLASH_BANK2_START)
    {
        if (!flash_wait_busy2())
            return 0;
        flash_clear_flags2();
        FLASH_CR2 |= FLASH_CR_PG;
        *((volatile uint16_t *)(uintptr_t)address) = data;
        uint8_t ok = flash_wait_busy2();
        if (ok)
            ok = (FLASH_SR2 & FLASH_SR_EOP) ? 1 : 0;
        FLASH_SR2  =  FLASH_SR_EOP;
        FLASH_CR2 &= ~FLASH_CR_PG;
        if (ok)  /* read-back verify */
            ok = (*((volatile uint16_t *)(uintptr_t)address) == data) ? 1 : 0;
        return ok;
    }
#endif
    /* Bank 1 path — all densities */
    if (!flash_wait_busy())
        return 0;
    flash_clear_flags();
    FLASH->cr |= FLASH_CR_PG;
    *((volatile uint16_t *)(uintptr_t)address) = data;
    uint8_t ok = flash_wait_busy();
    if (ok)
        ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  =  FLASH_SR_EOP;
    FLASH->cr &= ~FLASH_CR_PG;
    if (ok)  /* read-back verify — EOP says done, this says the cell holds it */
        ok = (*((volatile uint16_t *)(uintptr_t)address) == data) ? 1 : 0;
    return ok;
}

static uint8_t flash_write_word(uint32_t address, uint32_t data)
{
    if (address & 0x1)   /* halfword alignment only — word alignment not required */
        return 0;

#ifdef FLASH_XL_DENSITY
    if (address >= FLASH_BANK2_START)
    {
        /* Both halfwords in bank 2 */
        flash_unlock2();
        uint8_t ok = flash_write_halfword(address,     (uint16_t)(data & 0xFFFFU));
        if (ok)
            ok     = flash_write_halfword(address + 2, (uint16_t)(data >> 16));
        flash_lock2();
        return ok;
    }
    if (address + 2 >= FLASH_BANK2_START)
    {
        /* Straddles the bank seam (address == FLASH_BANK2_START - 2):
         * first halfword in bank 1, second in bank 2. flash_write_halfword
         * picks the bank per call, but both controllers must be unlocked. */
        flash_unlock();
        flash_unlock2();
        uint8_t ok = flash_write_halfword(address,     (uint16_t)(data & 0xFFFFU));
        if (ok)
            ok     = flash_write_halfword(address + 2, (uint16_t)(data >> 16));
        flash_lock();
        flash_lock2();
        return ok;
    }
#endif
    flash_unlock();
    uint8_t ok = flash_write_halfword(address,     (uint16_t)(data & 0xFFFFU));
    if (ok)
        ok     = flash_write_halfword(address + 2, (uint16_t)(data >> 16));
    flash_lock();
    return ok;
}

static uint8_t flash_erase_page(uint32_t address)
{
    /* Compute page base — the flash controller needs the exact page start
     * address in FLASH_AR, not an arbitrary address within the page. */
    uint32_t page_base = address & ~(FLASH_PAGE_SIZE - 1UL);

#ifdef FLASH_XL_DENSITY
    if (address >= FLASH_BANK2_START)
    {
        flash_unlock2();
        if (!flash_wait_busy2())
        {
            flash_lock2();
            return 0;
        }
        flash_clear_flags2();
        FLASH_CR2 |= FLASH_CR_PER;
        FLASH_AR2  = page_base;
        FLASH_CR2 |= FLASH_CR_STRT;
        uint8_t ok = flash_wait_busy2();
        if (ok)
            ok = (FLASH_SR2 & FLASH_SR_EOP) ? 1 : 0;
        FLASH_SR2  =  FLASH_SR_EOP;
        FLASH_CR2 &= ~FLASH_CR_PER;
        if (ok)
            ok = flash_page_blank(page_base);
        flash_lock2();
        return ok;
    }
#endif
    flash_unlock();
    if (!flash_wait_busy())
    {
        flash_lock();
        return 0;
    }
    flash_clear_flags();
    FLASH->cr |= FLASH_CR_PER;
    FLASH->ar  = page_base;
    FLASH->cr |= FLASH_CR_STRT;
    uint8_t ok = flash_wait_busy();
    if (ok)
        ok = (FLASH->sr & FLASH_SR_EOP) ? 1 : 0;
    FLASH->sr  =  FLASH_SR_EOP;
    FLASH->cr &= ~FLASH_CR_PER;
    if (ok)
        ok = flash_page_blank(page_base);
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
    /* ERASE ignores buffer and length entirely — handle before the null/length
     * guard so callers are not forced to supply a dummy payload. */
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
            if (address & 0x1)      /* halfword alignment required */
                return 0;

            if (!flash_is_erased(address, length))
                return 0;

            if (length <= 2)
            {
                /* Single halfword write */
                uint16_t hw;
                if (length == 2)
                    hw = (uint16_t)buffer[0] | ((uint16_t)buffer[1] << 8);
                else
                    hw = (uint16_t)buffer[0] | 0xFF00U; /* upper byte stays erased */

#ifdef FLASH_XL_DENSITY
                if (address >= FLASH_BANK2_START)
                {
                    flash_unlock2();
                    uint8_t ok = flash_write_halfword(address, hw);
                    flash_lock2();
                    return ok;
                }
#endif
                flash_unlock();
                uint8_t ok = flash_write_halfword(address, hw);
                flash_lock();
                return ok;
            }
            else
            {
                /* Pack up to 4 bytes into a word; upper bytes stay 0xFF if
                 * length < 4 (they will be written as erased-value padding). */
                uint32_t word = 0xFFFFFFFFUL;
                for (uint16_t i = 0; i < length && i < 4; i++)
                    word = (word & ~(0xFFUL << (i * 8))) | ((uint32_t)buffer[i] << (i * 8));
                return flash_write_word(address, word);
            }
        }

        case MDT_MEM_ZONE_ERASE:
            /* Unreachable — handled above before the switch.
             * Kept so the compiler does not warn on an unhandled enum value. */
            return flash_erase_page(address);

        default:
            return 0;
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

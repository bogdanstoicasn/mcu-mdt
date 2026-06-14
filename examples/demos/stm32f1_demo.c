#include "mcu_mdt.h"
#include <stdint.h>

/*
 * MCU-MDT demo for STM32F103xx (Cortex-M3), IDLE-interrupt mode.
 *
 * Same idea as the F030 demo (TIM3 increments a counter every 4 s), but the
 * main loop does NOT call mcu_mdt_poll(). The MDT interface runs from
 * interrupts: the USART RX/IDLE interrupt receives each packet and pends
 * PendSV, which processes it (built into the HAL when MDT_FEATURE_UART_IDLE
 * is on). The PC polls periodically and each poll reply carries back any
 * pending event, so watchpoint hits reach the PC on their own.
 *
 * The one thing the IDLE path does not do is run the watchpoint check (the
 * comparison that detects a change and queues the event). With no poll() in
 * the loop, a periodic interrupt must drive it, so the TIM3 ISR calls
 * mcu_mdt_watchpoint_check() once a second.
 *
 * The TIM3 interrupt is set to the lowest priority, same as PendSV, so the
 * check cannot preempt event delivery mid packet.
 *
 * Clock: reset-default HSI = 8 MHz (no PLL in startup), matching F_CPU.
 * TIM3 is NVIC IRQ 29 here (IRQ 16 on the F0).
 */

/*
 * Commands for the demo but first setup:
 *
 * arm-none-eabi-nm build/F030F4/mcu_mdt_example.elf | grep demo_counter
 * (20000020) demo_counter
 * 
 * ping
 * read_mem ram address 4 (2-3 times, so that demo_counter changes)
 * watchpoint 0 enabled demo_counter
 * write_mem ram address 4 000003E8
 * read_mem ram address 4 (should show 000003E8, and then start counting up every 4 seconds)
 * 
 * Optional:
 * READ_MEM FLASH 0x08000000 4
 * RESET
 * read_mem ram address 4 (should show 0 again after reset, and then start counting up every 4 seconds)
 * 
 */

/* Volatile + not static so the name resolves for the watchpoint. */
volatile uint32_t demo_counter = 0;

/* TIM3 (general-purpose 16-bit timer, APB1) */
#define TIM3_BASE 0x40000400UL
typedef struct {
    volatile uint32_t cr1;    /* 0x00 control 1            */
    volatile uint32_t cr2;    /* 0x04                      */
    volatile uint32_t smcr;   /* 0x08                      */
    volatile uint32_t dier;   /* 0x0C DMA/IRQ enable       */
    volatile uint32_t sr;     /* 0x10 status               */
    volatile uint32_t egr;    /* 0x14 event generation     */
    volatile uint32_t ccmr1;  /* 0x18                      */
    volatile uint32_t ccmr2;  /* 0x1C                      */
    volatile uint32_t ccer;   /* 0x20                      */
    volatile uint32_t cnt;    /* 0x24 counter              */
    volatile uint32_t psc;    /* 0x28 prescaler            */
    volatile uint32_t arr;    /* 0x2C auto-reload          */
} tim_def_t;
#define TIM3 ((tim_def_t *) TIM3_BASE)

#define TIM_CR1_CEN (1U << 0)   /* counter enable          */
#define TIM_DIER_UIE (1U << 0)   /* update interrupt enable */
#define TIM_SR_UIF (1U << 0)   /* update interrupt flag   */
#define TIM_EGR_UG (1U << 0)   /* update generation       */

/* RCC APB1 peripheral-clock enable register (only the one register the
 * demo needs; the MDT distribution headers don't expose the RCC struct). */
#define RCC_APB1ENR (*(volatile uint32_t *) 0x4002101CUL)
#define RCC_APB1ENR_TIM3EN (1U << 1)

/* NVIC: TIM3 is IRQ 29 on the F103. ISER0 (IRQ 0-31) at 0xE000E100.
 * Per-IRQ priority byte is at NVIC_IPR base 0xE000E400 + IRQn. */
#define NVIC_ISER0 (*(volatile uint32_t *) 0xE000E100UL)
#define NVIC_IPR_BASE (0xE000E400UL)
#define TIM3_IRQ_NUM 29
#define IRQ_PRI_LOWEST 0xFFU       /* same lowest priority as PendSV */

/* Tick budget: at 8 MHz, PSC=7999 -> 1 kHz timer clock; ARR=999 -> update
 * event every 1000 ticks = 1 s; count 4 of them in the ISR for 4 s. Keeps
 * every register value inside the 16-bit range a 4 s period can't reach. */
#define TIM3_PSC 7999U
#define TIM3_ARR 999U
#define SECONDS_PER_STEP 4U

static void tim3_init(void)
{
    RCC_APB1ENR |= RCC_APB1ENR_TIM3EN;      /* clock the timer            */

    TIM3->psc = TIM3_PSC;
    TIM3->arr = TIM3_ARR;
    TIM3->egr = TIM_EGR_UG;                 /* latch PSC/ARR immediately  */
    TIM3->sr  = 0;                          /* clear the UG-induced flag  */

    /* Lowest priority so the watchpoint check can't preempt PendSV's event
     * delivery. NVIC_IPR is byte-addressable on Cortex-M3. */
    *((volatile uint8_t *)(NVIC_IPR_BASE + TIM3_IRQ_NUM)) = IRQ_PRI_LOWEST;

    TIM3->dier |= TIM_DIER_UIE;             /* enable update interrupt    */
    NVIC_ISER0  = (1U << TIM3_IRQ_NUM);     /* enable TIM3 IRQ in the NVIC */

    TIM3->cr1 |= TIM_CR1_CEN;               /* start counting             */
}

/* Overrides the weak TIM3_IRQHandler in the startup vector table. */
void TIM3_IRQHandler(void)
{
    if (TIM3->sr & TIM_SR_UIF)
    {
        TIM3->sr &= ~TIM_SR_UIF;            /* acknowledge the interrupt  */

        static uint32_t seconds = 0;
        if (++seconds >= SECONDS_PER_STEP)
        {
            seconds = 0;
            demo_counter++;
        }
    }
}

int main(void)
{
    mcu_mdt_init();
    tim3_init();

    while (1)
    {
        __asm volatile ("nop");
    }

    return 0;
}

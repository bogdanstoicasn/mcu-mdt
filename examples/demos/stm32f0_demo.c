#include "mcu_mdt.h"
#include <stdint.h>

/*
 * MCU-MDT demo for STM32F030F4
 *
 * A general-purpose timer (TIM3) increments a counter by 1 every 4 seconds.
 * The counter lives at a fixed, named symbol so it can be watched live from
 * the PC tool without halting the core:
 *
 *     watchpoint 0 enabled demo_counter
 *
 * Clock assumption: the firmware runs on the reset-default HSI = 8 MHz (the
 * startup file installs no PLL), which matches the build's F_CPU. If you add
 * your own clock setup, recompute TIM3_PSC accordingly.
 */

/* Static and volatile so we can use the name with the watchpoints */
volatile uint32_t demo_counter = 0;

/* TIM3 (general-purpose 16-bit timer, APB1) */
#define TIM3_BASE        0x40000400UL
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
#define TIM3             ((tim_def_t *) TIM3_BASE)

#define TIM_CR1_CEN      (1U << 0)   /* counter enable          */
#define TIM_DIER_UIE     (1U << 0)   /* update interrupt enable */
#define TIM_SR_UIF       (1U << 0)   /* update interrupt flag   */
#define TIM_EGR_UG       (1U << 0)   /* update generation       */

/* RCC APB1 peripheral-clock enable register (only the one register the
 * demo needs; the MDT distribution headers don't expose the RCC struct). */
#define RCC_APB1ENR      (*(volatile uint32_t *) 0x4002101CUL)
#define RCC_APB1ENR_TIM3EN  (1U << 1)

/* NVIC: TIM3 is IRQ 16 on the F0. ISER lives at 0xE000E100. */
#define NVIC_ISER0       (*(volatile uint32_t *) 0xE000E100UL)
#define TIM3_IRQ_NUM     16

/* Tick budget: at 8 MHz, PSC=7999 gives a 1 kHz timer clock (divide by
 * PSC+1 = 8000), ARR=999 makes the timer raise an update event every
 * (ARR+1) = 1000 ticks = exactly 1 s. We then count 4 of those in the ISR.
 * Doing it this way keeps every register value inside the 16-bit range that
 * a 4 s period could not otherwise reach on a 16-bit timer. */
#define TIM3_PSC         7999U
#define TIM3_ARR          999U
#define SECONDS_PER_STEP    4U

static void tim3_init(void)
{
    RCC_APB1ENR |= RCC_APB1ENR_TIM3EN;      /* clock the timer            */

    TIM3->psc = TIM3_PSC;
    TIM3->arr = TIM3_ARR;
    TIM3->egr = TIM_EGR_UG;                 /* latch PSC/ARR immediately  */
    TIM3->sr  = 0;                          /* clear the UG-induced flag  */

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
            demo_counter++;                 /* the value the debugger sees */
        }
    }
}

int main(void)
{
    mcu_mdt_init();   /* brings up USART1 + the MDT command interface */
    tim3_init();      /* start the 4-second counter                  */

    while (1)
    {
        mcu_mdt_poll();
    }

    return 0;
}


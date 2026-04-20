#ifndef UART_H
#define UART_H

#include <stdint.h>

/* USART1 */
#define USART1_BASE 0x40013800UL

typedef struct {
    volatile uint32_t cr1;       /* 0x00 */
    volatile uint32_t cr2;       /* 0x04 */
    volatile uint32_t cr3;       /* 0x08 */
    volatile uint32_t brr;       /* 0x0C */
    volatile uint32_t reserved0; /* 0x10 */
    volatile uint32_t rtor;      /* 0x14 */
    volatile uint32_t rqr;       /* 0x18 */
    volatile uint32_t isr;       /* 0x1C */
    volatile uint32_t icr;       /* 0x20 */
    volatile uint32_t rdr;       /* 0x24 */
    volatile uint32_t tdr;       /* 0x28 */
} usart_def_t;

#define USART1 ((volatile usart_def_t *) USART1_BASE)

/* CR1 bits */
#define USART_CR1_UE      (1U << 0)
#define USART_CR1_RE      (1U << 2)
#define USART_CR1_TE      (1U << 3)
#define USART_CR1_IDLEIE  (1U << 4)
#define USART_CR1_RXNEIE  (1U << 5)
#define USART_CR1_TXEIE   (1U << 7)

/* ISR bits */
#define USART_ISR_ORE     (1U << 3)
#define USART_ISR_IDLE    (1U << 4)
#define USART_ISR_RXNE    (1U << 5)
#define USART_ISR_TXE     (1U << 7)

/* ICR bits */
#define USART_ICR_ORECF   (1U << 3)
#define USART_ICR_IDLECF  (1U << 4)

/* RCC */

#define RCC_BASE 0x40021000UL

typedef struct {
    volatile uint32_t cr;       /* 0x00 */
    volatile uint32_t cfgr;     /* 0x04 */
    volatile uint32_t cir;      /* 0x08 */
    volatile uint32_t apb2rstr; /* 0x0C */
    volatile uint32_t apb1rstr; /* 0x10 */
    volatile uint32_t ahbenr;   /* 0x14 */
    volatile uint32_t apb2enr;  /* 0x18 */
    volatile uint32_t apb1enr;  /* 0x1C */
    volatile uint32_t bdcr;     /* 0x20 */
    volatile uint32_t csr;      /* 0x24 */
    volatile uint32_t ahbrstr;  /* 0x28 */
    volatile uint32_t cfgr2;    /* 0x2C */
    volatile uint32_t cfgr3;    /* 0x30 */
    volatile uint32_t cr2;      /* 0x34 */
} rcc_def_t;

#define RCC ((volatile rcc_def_t *) RCC_BASE)

#define RCC_AHBENR_GPIOAEN    (1U << 17)
#define RCC_APB2ENR_USART1EN  (1U << 14)

/* GPIOA*/

#define GPIOA_BASE 0x48000000UL

typedef struct {
    volatile uint32_t moder;   /* 0x00 */
    volatile uint32_t otyper;  /* 0x04 */
    volatile uint32_t ospeedr; /* 0x08 */
    volatile uint32_t pupdr;   /* 0x0C */
    volatile uint32_t idr;     /* 0x10 */
    volatile uint32_t odr;     /* 0x14 */
    volatile uint32_t bsrr;    /* 0x18 */
    volatile uint32_t lckr;    /* 0x1C */
    volatile uint32_t afrl;    /* 0x20 */
    volatile uint32_t afrh;    /* 0x24 */
    volatile uint32_t brr;     /* 0x28 */
} gpio_def_t;

#define GPIOA ((volatile gpio_def_t *) GPIOA_BASE)

/* GPIO MODER */
#define GPIO_MODER_AF    2U
#define GPIO_MODER_MASK  3U

/* Alternate function 1 = USART1 */
#define GPIO_AF1         1U

/* USART1 pins */
#define USART1_TX_PIN        9U
#define USART1_RX_PIN        10U
#define USART1_TX_AFRH_POS   4U   /* PA9  in AFRH bits 7:4  */
#define USART1_RX_AFRH_POS   8U  /* PA10 in AFRH bits 11:8 */

/* NVIC */
#define NVIC_ISER        ((volatile uint32_t *)0xE000E100)
#define USART1_IRQ       27

/* Cortex-M0 System Control Block — for PendSV */
#define SCB_ICSR         (*((volatile uint32_t *)0xE000ED04UL))
/* On Cortex-M0, PendSV is exception 14.
 * System handler priorities are in SHP[0..7] at 0xE000ED18.
 * SHP[2] at 0xE000ED20 covers exceptions 12-15: bits 23:16 = PendSV priority. */
#define SCB_SHP3         (*((volatile uint32_t *)0xE000ED20UL))
#define SCB_PENDSV_SET   (1U << 28)
#define PENDSV_PRI_LOWEST (0xFFU << 16)  /* bits 23:16 of SHP[2] = PendSV pri */

#endif /* UART_H */
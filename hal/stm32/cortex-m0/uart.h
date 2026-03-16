#ifndef UART_H
#define UART_H

#include <stdint.h>

/* STM-private UART driver */
void uart_init(uint32_t baudrate);
uint8_t uart_putc(uint8_t data);
uint8_t uart_getc_nonblocking(uint8_t *data);
uint8_t uart_ready(void);

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
#define USART_CR1_RXNEIE  (1U << 5)
#define USART_CR1_TXEIE   (1U << 7)

/* ISR bits */
#define USART_ISR_ORE     (1U << 3)
#define USART_ISR_RXNE    (1U << 5)
#define USART_ISR_TXE     (1U << 7)

/* ICR bits */
#define USART_ICR_ORECF   (1U << 3)

/* RCC */

#define RCC_BASE 0x40021000UL

typedef struct {
    volatile uint32_t cr;
    volatile uint32_t cfgr;
    volatile uint32_t cir;
    volatile uint32_t apb2rstr;
    volatile uint32_t apb1rstr;
    volatile uint32_t ahbenr;
    volatile uint32_t apb2enr;
    volatile uint32_t apb1enr;
    volatile uint32_t bdcr;
    volatile uint32_t csr;
    volatile uint32_t ahbrstr;
    volatile uint32_t cfgr2;
    volatile uint32_t cfgr3;
    volatile uint32_t cr2;
} rcc_def_t;

#define RCC ((volatile rcc_def_t *) RCC_BASE)

#define RCC_AHBENR_GPIOAEN    (1U << 17)
#define RCC_APB2ENR_USART1EN  (1U << 14)

/* GPIOA*/

#define GPIOA_BASE 0x48000000UL

typedef struct {
    volatile uint32_t moder;
    volatile uint32_t otyper;
    volatile uint32_t ospeedr;
    volatile uint32_t pupdr;
    volatile uint32_t idr;
    volatile uint32_t odr;
    volatile uint32_t bsrr;
    volatile uint32_t lckr;
    volatile uint32_t afrl;
    volatile uint32_t afrh;
    volatile uint32_t brr;
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

#endif /* UART_H */
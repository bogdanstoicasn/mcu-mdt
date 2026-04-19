#ifndef UART_H
#define UART_H

#include <stdint.h>

/* STM-private UART driver */
void uart_init(uint32_t baudrate);
uint8_t uart_putc(uint8_t data);
uint8_t uart_getc_nonblocking(uint8_t *data);
uint8_t uart_ready(void);
uint8_t uart_tx_empty(void);
uint8_t uart_rx_overflow(void);

/* USART1 */
#define USART1_BASE 0x40013800UL

typedef struct {
    volatile uint32_t sr;   /* 0x00 */
    volatile uint32_t dr;   /* 0x04 */
    volatile uint32_t brr;  /* 0x08 */
    volatile uint32_t cr1;  /* 0x0C */
    volatile uint32_t cr2;  /* 0x10 */
    volatile uint32_t cr3;  /* 0x14 */
    volatile uint32_t gtpr; /* 0x18 */
} usart_def_t;

#define USART1 ((volatile usart_def_t *) USART1_BASE)

#define USART_CR1_UE (1U << 13)
#define USART_CR1_RE (1U << 2)
#define USART_CR1_TE (1U << 3)
#define USART_CR1_IDLEIE  (1U << 4)
#define USART_CR1_RXNEIE  (1U << 5)
#define USART_CR1_TXEIE   (1U << 7)

#define USART_SR_ORE    (1U << 3)
#define USART_SR_IDLE   (1U << 4)
#define USART_SR_RXNE   (1U << 5)
#define USART_SR_TXE    (1U << 7)

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

    /* Connectivity only devices */
    volatile uint32_t ahbrstr;  /* 0x28 */
    volatile uint32_t cfgr2;    /* 0x2C */
} rcc_def_t;

#define RCC ((volatile rcc_def_t *) RCC_BASE)

#define RCC_APB2ENR_AFIOEN    (1U << 0)   /* Alternate function I/O clock */
#define RCC_APB2ENR_IOPAEN    (1U << 2)   /* GPIOA clock APB2 */
#define RCC_APB2ENR_USART1EN  (1U << 14)  /* USART1 clock */

/* GPIOA */
#define GPIOA_BASE 0x40010800UL

typedef struct {
    volatile uint32_t crl;  /* 0x00 */
    volatile uint32_t crh;  /* 0x04 */
    volatile uint32_t idr;  /* 0x08 */
    volatile uint32_t odr;  /* 0x0C */
    volatile uint32_t bsrr; /* 0x10 */
    volatile uint32_t brr;  /* 0x14 */
    volatile uint32_t lckr; /* 0x18 */

} gpio_def_t;

#define GPIOA ((volatile gpio_def_t *) GPIOA_BASE)


/* NVIC */
#define NVIC_ISER  ((volatile uint32_t *)0xE000E100)
#define USART1_IRQ 37

/* Cortex-M3 System Control Block — for PendSV */
#define SCB_ICSR         (*((volatile uint32_t *)0xE000ED04UL))

#define SCB_SHP3         (*((volatile uint32_t *)0xE000ED20UL))
#define SCB_PENDSV_SET   (1U << 28)
#define PENDSV_PRI_LOWEST (0xFFU << 16)  /* bits 23:16 of SHP[2] = PendSV pri */


#endif
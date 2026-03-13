#ifndef UART_H
#define UART_H

#include <stdint.h>

/* STM-private UART driver */
void uart_init(uint32_t baudrate);
uint8_t uart_putc(uint8_t data);
uint8_t uart_getc_nonblocking(uint8_t *data);
uint8_t uart_ready();

/* Defines and addresses */

/* USART1 zone */
#define USART1_BASE 0x40013800

typedef struct {
    volatile uint32_t cr1;
    volatile uint32_t cr2;
    volatile uint32_t cr3;
    volatile uint32_t brr;
    volatile uint32_t rtor;
    volatile uint32_t rqr;
    volatile uint32_t isr;
    volatile uint32_t icr;
    volatile uint32_t rdr;
    volatile uint32_t tdr;
} usart_def_t;

#define USART1 ((volatile usart_def_t *) USART1_BASE)

/* Bit definitions */

#define USART_CR1_UE      (1 << 0)
#define USART_CR1_RE      (1 << 2)
#define USART_CR1_TE      (1 << 3)
#define USART_CR1_RXNEIE  (1 << 5)
#define USART_CR1_TXEIE   (1 << 7)

#define USART_ISR_RXNE    (1 << 5)
#define USART_ISR_TXE     (1 << 7)
/* End of USART1 zone */

/* RCC zone */
#define RCC_BASE 0x40021000

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

#define RCC_AHBENR_GPIOAEN   (1 << 17)
#define RCC_APB2ENR_USART1EN (1 << 14)
/* End of RCC zone */

/* GPIO zone */
#define GPIOA_BASE 0x48000000

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
/* End of GPIO zone */

/* NVIC zone */
#define NVIC_BASE 0xE000E000
/* End of NVIC zone */
#define NVIC_ISER ((volatile uint32_t*)0xE000E100)
#define USART1_IRQ 27

#endif // UART_H

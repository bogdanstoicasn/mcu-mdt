#include <stdint.h>

/* Linker script symbols*/
extern uint32_t _stack; /* Stack */

extern uint32_t _etext; /* End of text section */
extern uint32_t _sdata; /* Start of data section */
extern uint32_t _edata; /* End of data section */

extern uint32_t _sbss; /* Start of bss section */
extern uint32_t _ebss; /* End of bss section */

/* Forward declarations */
int main(void);
void Reset_Handler(void) __attribute__((noreturn, naked));
static void Default_Handler(void);

void NMI_Handler(void) __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void) __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void) __attribute__((weak, alias("Default_Handler")));

void USART1_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));

/* Vector table */
__attribute__((used, section(".vectors")))
const void* const vector_table[] = {
    &_stack,                   /* Initial stack pointer */ /* 0x00 */
    Reset_Handler,             /* Reset handler */         /* 0x04 */
    NMI_Handler,               /* NMI handler */           /* 0x08 */
    HardFault_Handler,         /* Hard fault handler */    /* 0x0C */
    0,                         /* Reserved */              /* 0x10 */
    0,                         /* Reserved */              /* 0x14 */
    0,                         /* Reserved */              /* 0x18 */
    0,                         /* Reserved */              /* 0x1C */
    0,                         /* Reserved */              /* 0x20 */
    0,                         /* Reserved */              /* 0x24 */
    0,                         /* Reserved */              /* 0x28 */
    SVC_Handler,               /* SVCall handler */        /* 0x2C */
    0,                         /* Reserved */              /* 0x30 */
    0,                         /* Reserved */              /* 0x34 */
    PendSV_Handler,           /* PendSV handler */         /* 0x38 */
    SysTick_Handler,          /* SysTick handler */        /* 0x3C */

    /* IRQ 0 -> IRQ 31*/
    Default_Handler,           /* IRQ 0 - WWDG */          /* 0x40 */
    0,                         /* IRQ 1 - RESERVED */      /* 0x44 */
    Default_Handler,           /* IRQ 2 - RTC */           /* 0x48 */
    Default_Handler,           /* IRQ 3 - FLASH */         /* 0x4C */
    Default_Handler,           /* IRQ 4 - RCC */           /* 0x50 */
    Default_Handler,           /* IRQ 5 - EXTI0_1 */       /* 0x54 */
    Default_Handler,           /* IRQ 6 - EXTI2_3 */       /* 0x58 */
    Default_Handler,           /* IRQ 7 - EXTI4_15 */      /* 0x5C */
    0,                         /* IRQ 8 - RESERVED */      /* 0x60 */
    Default_Handler,           /* IRQ 9 - DMA_CH1 */       /* 0x64 */
    Default_Handler,           /* IRQ 10 - DMA_CH2_3 */    /* 0x68 */
    Default_Handler,           /* IRQ 11 - DMA_CH4_5 */    /* 0x6C */
    Default_Handler,           /* IRQ 12 - ADC */          /* 0x70 */
    Default_Handler,           /* IRQ 13 - TIM1_BRK_UP_TRG_COM */ /* 0x74 */
    Default_Handler,           /* IRQ 14 - TIM1_CC */      /* 0x78 */
    0,                         /* IRQ 15 - RESERVED */     /* 0x7C */
    Default_Handler,           /* IRQ 16 - TIM3 */         /* 0x80 */
    Default_Handler,           /* IRQ 17 - TIM6 */         /* 0x84 */
    0,                         /* IRQ 18 - RESERVED */     /* 0x88 */
    Default_Handler,           /* IRQ 19 - TIM14 */        /* 0x8C */
    Default_Handler,           /* IRQ 20 - TIM15 */        /* 0x90 */
    Default_Handler,           /* IRQ 21 - TIM16 */        /* 0x94 */
    Default_Handler,           /* IRQ 22 - TIM17 */        /* 0x98 */
    Default_Handler,           /* IRQ 23 - I2C1 */         /* 0x9C */
    Default_Handler,           /* IRQ 24 - I2C2 */         /* 0xA0 */
    Default_Handler,           /* IRQ 25 - SPI1 */         /* 0xA4 */
    Default_Handler,           /* IRQ 26 - SPI2 */         /* 0xA8 */
    USART1_IRQHandler,         /* IRQ 27 - USART1 */       /* 0xAC */
    Default_Handler,           /* IRQ 28 - USART2 */       /* 0xB0 */
    Default_Handler,           /* IRQ 29 - USART3_4_5_6 */ /* 0xB4 */
    0,                         /* IRQ 30 - RESERVED */     /* 0xB8 */
    Default_Handler,           /* IRQ 31 - USB */          /* 0xBC */
};


/* Reset Handler */
void Reset_Handler(void)
{
    /* Copy data section from flash to RAM */
    uint32_t* src = &_etext;
    uint32_t* dst = &_sdata;
    
    while (dst < &_edata)
    {
        *dst++ = *src++;
    }

    /* Zero out the bss section */
    dst = &_sbss;
    while (dst < &_ebss)
    {
        *dst++ = 0;
    }

    /* Call the main function */
    main();

    while (1)
    {
        /* Infinite loop to prevent returning from main */
    }
}

/* Default Handler */
void Default_Handler(void)
{
    while (1)
    {
        /* Infinite loop to indicate an unhandled exception */
    }
}
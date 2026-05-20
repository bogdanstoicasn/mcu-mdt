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

/* Core exceptions */
void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));

/* IRQ handlers */
void WWDG_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void RTC_IRQHandler(void)                   __attribute__((weak, alias("Default_Handler")));
void FLASH_IRQHandler(void)                 __attribute__((weak, alias("Default_Handler")));
void RCC_IRQHandler(void)                   __attribute__((weak, alias("Default_Handler")));
void EXTI0_1_IRQHandler(void)               __attribute__((weak, alias("Default_Handler")));
void EXTI2_3_IRQHandler(void)               __attribute__((weak, alias("Default_Handler")));
void EXTI4_15_IRQHandler(void)              __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel1_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel2_3_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel4_5_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void ADC1_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void TIM1_BRK_UP_TRG_COM_IRQHandler(void)   __attribute__((weak, alias("Default_Handler")));
void TIM1_CC_IRQHandler(void)               __attribute__((weak, alias("Default_Handler")));
void TIM3_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void TIM6_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void TIM14_IRQHandler(void)                 __attribute__((weak, alias("Default_Handler")));
void TIM15_IRQHandler(void)                 __attribute__((weak, alias("Default_Handler")));
void TIM16_IRQHandler(void)                 __attribute__((weak, alias("Default_Handler")));
void TIM17_IRQHandler(void)                 __attribute__((weak, alias("Default_Handler")));
void I2C1_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void I2C2_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void SPI1_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void SPI2_IRQHandler(void)                  __attribute__((weak, alias("Default_Handler")));
void USART1_IRQHandler(void)                __attribute__((weak, alias("Default_Handler")));
void USART2_IRQHandler(void)                __attribute__((weak, alias("Default_Handler")));
void USART3_4_5_6_IRQHandler(void)          __attribute__((weak, alias("Default_Handler")));
void USB_IRQHandler(void)                   __attribute__((weak, alias("Default_Handler")));

/* Vector table */
__attribute__((used, section(".vectors")))
const void* const vector_table[] = {
    &_stack,                          /* Initial stack pointer */      /* 0x00 */
    Reset_Handler,                    /* Reset handler */               /* 0x04 */
    NMI_Handler,                      /* NMI handler */                 /* 0x08 */
    HardFault_Handler,                /* Hard fault handler */          /* 0x0C */
    0,                                /* Reserved */                    /* 0x10 */
    0,                                /* Reserved */                    /* 0x14 */
    0,                                /* Reserved */                    /* 0x18 */
    0,                                /* Reserved */                    /* 0x1C */
    0,                                /* Reserved */                    /* 0x20 */
    0,                                /* Reserved */                    /* 0x24 */
    0,                                /* Reserved */                    /* 0x28 */
    SVC_Handler,                      /* SVCall handler */              /* 0x2C */
    0,                                /* Reserved */                    /* 0x30 */
    0,                                /* Reserved */                    /* 0x34 */
    PendSV_Handler,                   /* PendSV handler */              /* 0x38 */
    SysTick_Handler,                  /* SysTick handler */             /* 0x3C */

    /* IRQ 0 -> IRQ 31*/
    WWDG_IRQHandler,                  /* IRQ 0 - WWDG */                /* 0x40 */
    0,                                /* IRQ 1 - RESERVED */            /* 0x44 */
    RTC_IRQHandler,                   /* IRQ 2 - RTC */                 /* 0x48 */
    FLASH_IRQHandler,                 /* IRQ 3 - FLASH */               /* 0x4C */
    RCC_IRQHandler,                   /* IRQ 4 - RCC */                 /* 0x50 */
    EXTI0_1_IRQHandler,               /* IRQ 5 - EXTI0_1 */             /* 0x54 */
    EXTI2_3_IRQHandler,               /* IRQ 6 - EXTI2_3 */             /* 0x58 */
    EXTI4_15_IRQHandler,              /* IRQ 7 - EXTI4_15 */            /* 0x5C */
    0,                                /* IRQ 8 - RESERVED */            /* 0x60 */
    DMA1_Channel1_IRQHandler,         /* IRQ 9 - DMA_CH1 */             /* 0x64 */
    DMA1_Channel2_3_IRQHandler,       /* IRQ 10 - DMA_CH2_3 */          /* 0x68 */
    DMA1_Channel4_5_IRQHandler,       /* IRQ 11 - DMA_CH4_5 */          /* 0x6C */
    ADC1_IRQHandler,                  /* IRQ 12 - ADC */                /* 0x70 */
    TIM1_BRK_UP_TRG_COM_IRQHandler,   /* IRQ 13 - TIM1_BRK_UP_TRG_COM */ /* 0x74 */
    TIM1_CC_IRQHandler,               /* IRQ 14 - TIM1_CC */            /* 0x78 */
    0,                                /* IRQ 15 - RESERVED */           /* 0x7C */
    TIM3_IRQHandler,                  /* IRQ 16 - TIM3 */               /* 0x80 */
    TIM6_IRQHandler,                  /* IRQ 17 - TIM6 */               /* 0x84 */
    0,                                /* IRQ 18 - RESERVED */           /* 0x88 */
    TIM14_IRQHandler,                 /* IRQ 19 - TIM14 */              /* 0x8C */
    TIM15_IRQHandler,                 /* IRQ 20 - TIM15 */              /* 0x90 */
    TIM16_IRQHandler,                 /* IRQ 21 - TIM16 */              /* 0x94 */
    TIM17_IRQHandler,                 /* IRQ 22 - TIM17 */              /* 0x98 */
    I2C1_IRQHandler,                  /* IRQ 23 - I2C1 */               /* 0x9C */
    I2C2_IRQHandler,                  /* IRQ 24 - I2C2 */               /* 0xA0 */
    SPI1_IRQHandler,                  /* IRQ 25 - SPI1 */               /* 0xA4 */
    SPI2_IRQHandler,                  /* IRQ 26 - SPI2 */               /* 0xA8 */
    USART1_IRQHandler,                /* IRQ 27 - USART1 */             /* 0xAC */
    USART2_IRQHandler,                /* IRQ 28 - USART2 */             /* 0xB0 */
    USART3_4_5_6_IRQHandler,          /* IRQ 29 - USART3_4_5_6 */       /* 0xB4 */
    0,                                /* IRQ 30 - RESERVED */           /* 0xB8 */
    USB_IRQHandler,                   /* IRQ 31 - USB */                /* 0xBC */
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
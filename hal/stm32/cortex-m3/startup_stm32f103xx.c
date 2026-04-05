#include <stdint.h>


#if defined(MCU_F103x4) || defined(MCU_F103x6)
  #define DENSITY_LD
#elif defined(MCU_F103xC) || defined(MCU_F103xD) || defined(MCU_F103xE)
  #define DENSITY_HD
#elif defined(MCU_F103xF) || defined(MCU_F103xG)
  #define DENSITY_XL
#elif defined(MCU_F105xx) || defined(MCU_F107xx)
  #define DENSITY_CL        /* Connectivity line (F105/F107) */
#else
  /* Medium-density is the default (covers F103x8 / F103xB, e.g. Blue Pill) */
  #define DENSITY_MD
#endif


extern uint32_t _stack;   /* Top of SRAM  (initial SP)              */
extern uint32_t _etext;   /* End of .text in Flash (LMA of .data)   */
extern uint32_t _sdata;   /* Start of .data in RAM (VMA)            */
extern uint32_t _edata;   /* End   of .data in RAM                  */
extern uint32_t _sbss;    /* Start of .bss  in RAM                  */
extern uint32_t _ebss;    /* End   of .bss  in RAM                  */


void Reset_Handler(void) __attribute__((noreturn, naked));
static void Default_Handler(void);

/* Cortex-M3 core handlers */
void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));

/* IRQ0–IRQ18: identical on every density tier */
void WWDG_IRQHandler(void)          __attribute__((weak, alias("Default_Handler")));
void PVD_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void TAMPER_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void RTC_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void FLASH_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void RCC_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void EXTI0_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void EXTI1_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void EXTI2_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void EXTI3_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void EXTI4_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel1_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel2_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel3_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel4_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel5_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel6_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void DMA1_Channel7_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void ADC1_2_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));

/* IRQ19–IRQ22: USB/CAN mux (LD/MD/HD/XL) or dedicated CAN1 (CL) */
#if defined(DENSITY_CL)
void CAN1_TX_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void CAN1_RX0_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void CAN1_RX1_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void CAN1_SCE_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
#else
void USB_HP_CAN_TX_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void USB_LP_CAN_RX0_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));
void CAN_RX1_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void CAN_SCE_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
#endif

/* IRQ23–IRQ27: EXTI9_5 and TIM1 (name varies on XL) */
void EXTI9_5_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
#if defined(DENSITY_XL)
/* On XL, TIM1 break/update/trigger slots are shared with TIM9/10/11        */
void TIM1_BRK_TIM9_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void TIM1_UP_TIM10_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void TIM1_TRG_COM_TIM11_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
#else
/* All other densities including CL use plain TIM1 names                    */
void TIM1_BRK_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void TIM1_UP_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void TIM1_TRG_COM_IRQHandler(void)   __attribute__((weak, alias("Default_Handler")));
#endif
void TIM1_CC_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));

/* IRQ28–IRQ42: shared by all densities */
void TIM2_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void TIM3_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void TIM4_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void I2C1_EV_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void I2C1_ER_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void I2C2_EV_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void I2C2_ER_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void SPI1_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void SPI2_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void USART1_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void USART2_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void USART3_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void EXTI15_10_IRQHandler(void)      __attribute__((weak, alias("Default_Handler")));
void RTCAlarm_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
/* IRQ42: OTG_FS_WKUP on CL; USBWakeUp on all other densities              */
#if defined(DENSITY_CL)
void OTG_FS_WKUP_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
#else
void USBWakeUp_IRQHandler(void)      __attribute__((weak, alias("Default_Handler")));
#endif

/* IRQ43+: HD and XL only (LD/MD table ends at IRQ42) */

/* TIM8_CC is the same name on both HD and XL                               */
#if defined(DENSITY_HD) || defined(DENSITY_XL)
void TIM8_CC_IRQHandler(void)               __attribute__((weak, alias("Default_Handler")));
#endif
/* TIM8 break/update/trigger: plain names on HD; share TIM12/13/14 on XL   */
#if defined(DENSITY_HD)
void TIM8_BRK_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void TIM8_UP_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void TIM8_TRG_COM_IRQHandler(void)   __attribute__((weak, alias("Default_Handler")));
#elif defined(DENSITY_XL)
void TIM8_BRK_TIM12_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void TIM8_UP_TIM13_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
void TIM8_TRG_COM_TIM14_IRQHandler(void)    __attribute__((weak, alias("Default_Handler")));
#endif

/* IRQ47–IRQ49: ADC3/FSMC/SDIO present on HD and XL only                   */
#if defined(DENSITY_HD) || defined(DENSITY_XL)
void ADC3_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void FSMC_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void SDIO_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
#endif

/* IRQ50–IRQ58: present on HD, XL, and CL                                  */
#if defined(DENSITY_HD) || defined(DENSITY_XL) || defined(DENSITY_CL)
void TIM5_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void SPI3_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void UART4_IRQHandler(void)          __attribute__((weak, alias("Default_Handler")));
void UART5_IRQHandler(void)          __attribute__((weak, alias("Default_Handler")));
void TIM6_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void TIM7_IRQHandler(void)           __attribute__((weak, alias("Default_Handler")));
void DMA2_Channel1_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void DMA2_Channel2_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void DMA2_Channel3_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
/* IRQ59: CL splits Ch4 and Ch5; HD/XL combine them into one handler        */
#  if defined(DENSITY_CL)
void DMA2_Channel4_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
void DMA2_Channel5_IRQHandler(void)  __attribute__((weak, alias("Default_Handler")));
#  else
void DMA2_Channel4_5_IRQHandler(void)__attribute__((weak, alias("Default_Handler")));
#  endif
#endif

/* IRQ60–IRQ67: connectivity line only (ETH, CAN2, OTG_FS)                 */
#if defined(DENSITY_CL)
void ETH_IRQHandler(void)            __attribute__((weak, alias("Default_Handler")));
void ETH_WKUP_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void CAN2_TX_IRQHandler(void)        __attribute__((weak, alias("Default_Handler")));
void CAN2_RX0_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void CAN2_RX1_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void CAN2_SCE_IRQHandler(void)       __attribute__((weak, alias("Default_Handler")));
void OTG_FS_IRQHandler(void)         __attribute__((weak, alias("Default_Handler")));
#endif



__attribute__((used, section(".vectors")))
const void* const vector_table[] =
{
    /* Cortex-M3 core */
    &_stack,                    /* 0x000 - Initial stack pointer              */
    Reset_Handler,              /* 0x004 - Reset                              */
    NMI_Handler,                /* 0x008 - NMI                                */
    HardFault_Handler,          /* 0x00C - Hard fault                         */
    MemManage_Handler,          /* 0x010 - Memory management fault            */
    BusFault_Handler,           /* 0x014 - Bus fault                          */
    UsageFault_Handler,         /* 0x018 - Usage fault                        */
    0,                          /* 0x01C - Reserved                           */
    0,                          /* 0x020 - Reserved                           */
    0,                          /* 0x024 - Reserved                           */
    0,                          /* 0x028 - Reserved                           */
    SVC_Handler,                /* 0x02C - SVCall                             */
    DebugMon_Handler,           /* 0x030 - Debug monitor                      */
    0,                          /* 0x034 - Reserved                           */
    PendSV_Handler,             /* 0x038 - PendSV                             */
    SysTick_Handler,            /* 0x03C - SysTick                            */

    /* Peripheral IRQs */
    /*
     * IRQ0–IRQ18 are identical across all density tiers and the connectivity
     * line.  Divergence begins at IRQ19.
     */

    /* IRQ0  0x0040 */ WWDG_IRQHandler,          /* Window watchdog                 */
    /* IRQ1  0x0044 */ PVD_IRQHandler,            /* PVD via EXTI                   */
    /* IRQ2  0x0048 */ TAMPER_IRQHandler,         /* Tamper                         */
    /* IRQ3  0x004C */ RTC_IRQHandler,            /* RTC global                     */
    /* IRQ4  0x0050 */ FLASH_IRQHandler,          /* Flash global                   */
    /* IRQ5  0x0054 */ RCC_IRQHandler,            /* RCC global                     */
    /* IRQ6  0x0058 */ EXTI0_IRQHandler,          /* EXTI Line 0                    */
    /* IRQ7  0x005C */ EXTI1_IRQHandler,          /* EXTI Line 1                    */
    /* IRQ8  0x0060 */ EXTI2_IRQHandler,          /* EXTI Line 2                    */
    /* IRQ9  0x0064 */ EXTI3_IRQHandler,          /* EXTI Line 3                    */
    /* IRQ10 0x0068 */ EXTI4_IRQHandler,          /* EXTI Line 4                    */
    /* IRQ11 0x006C */ DMA1_Channel1_IRQHandler,  /* DMA1 Ch1                       */
    /* IRQ12 0x0070 */ DMA1_Channel2_IRQHandler,  /* DMA1 Ch2                       */
    /* IRQ13 0x0074 */ DMA1_Channel3_IRQHandler,  /* DMA1 Ch3                       */
    /* IRQ14 0x0078 */ DMA1_Channel4_IRQHandler,  /* DMA1 Ch4                       */
    /* IRQ15 0x007C */ DMA1_Channel5_IRQHandler,  /* DMA1 Ch5                       */
    /* IRQ16 0x0080 */ DMA1_Channel6_IRQHandler,  /* DMA1 Ch6                       */
    /* IRQ17 0x0084 */ DMA1_Channel7_IRQHandler,  /* DMA1 Ch7                       */
    /* IRQ18 0x0088 */ ADC1_2_IRQHandler,         /* ADC1 & ADC2 global             */

/* IRQ19 onward: density-specific  */

#if defined(DENSITY_CL)
    /*
     * Connectivity line (Table 61).
     * IRQ19–22: CAN1 gets three dedicated slots instead of sharing with USB.
     * IRQ43–49: reserved gap (0x00EC–0x0104) between OTG_FS_WKUP and TIM5.
     * IRQ59–60: DMA2 Ch4 and Ch5 are two SEPARATE entries (not combined).
     */
    /* IRQ19 0x008C */ CAN1_TX_IRQHandler,        /* CAN1 TX                        */
    /* IRQ20 0x0090 */ CAN1_RX0_IRQHandler,       /* CAN1 RX0                       */
    /* IRQ21 0x0094 */ CAN1_RX1_IRQHandler,       /* CAN1 RX1                       */
    /* IRQ22 0x0098 */ CAN1_SCE_IRQHandler,       /* CAN1 SCE                       */
    /* IRQ23 0x009C */ EXTI9_5_IRQHandler,        /* EXTI Lines 9:5                 */
    /* IRQ24 0x00A0 */ TIM1_BRK_IRQHandler,       /* TIM1 Break                     */
    /* IRQ25 0x00A4 */ TIM1_UP_IRQHandler,        /* TIM1 Update                    */
    /* IRQ26 0x00A8 */ TIM1_TRG_COM_IRQHandler,   /* TIM1 Trigger & Commutation     */
    /* IRQ27 0x00AC */ TIM1_CC_IRQHandler,        /* TIM1 Capture Compare           */
    /* IRQ28 0x00B0 */ TIM2_IRQHandler,           /* TIM2 global                    */
    /* IRQ29 0x00B4 */ TIM3_IRQHandler,           /* TIM3 global                    */
    /* IRQ30 0x00B8 */ TIM4_IRQHandler,           /* TIM4 global                    */
    /* IRQ31 0x00BC */ I2C1_EV_IRQHandler,        /* I2C1 event                     */
    /* IRQ32 0x00C0 */ I2C1_ER_IRQHandler,        /* I2C1 error                     */
    /* IRQ33 0x00C4 */ I2C2_EV_IRQHandler,        /* I2C2 event                     */
    /* IRQ34 0x00C8 */ I2C2_ER_IRQHandler,        /* I2C2 error                     */
    /* IRQ35 0x00CC */ SPI1_IRQHandler,           /* SPI1 global                    */
    /* IRQ36 0x00D0 */ SPI2_IRQHandler,           /* SPI2 global                    */
    /* IRQ37 0x00D4 */ USART1_IRQHandler,         /* USART1 global                  */
    /* IRQ38 0x00D8 */ USART2_IRQHandler,         /* USART2 global                  */
    /* IRQ39 0x00DC */ USART3_IRQHandler,         /* USART3 global                  */
    /* IRQ40 0x00E0 */ EXTI15_10_IRQHandler,      /* EXTI Lines 15:10               */
    /* IRQ41 0x00E4 */ RTCAlarm_IRQHandler,       /* RTC alarm via EXTI             */
    /* IRQ42 0x00E8 */ OTG_FS_WKUP_IRQHandler,   /* USB OTG FS wakeup via EXTI      */
                       0, 0, 0, 0, 0, 0, 0,     /* IRQ43–49: 0x00EC–0x0104 Rsvd     */
    /* IRQ50 0x0108 */ TIM5_IRQHandler,           /* TIM5 global                    */
    /* IRQ51 0x010C */ SPI3_IRQHandler,           /* SPI3 global                    */
    /* IRQ52 0x0110 */ UART4_IRQHandler,          /* UART4 global                   */
    /* IRQ53 0x0114 */ UART5_IRQHandler,          /* UART5 global                   */
    /* IRQ54 0x0118 */ TIM6_IRQHandler,           /* TIM6 global                    */
    /* IRQ55 0x011C */ TIM7_IRQHandler,           /* TIM7 global                    */
    /* IRQ56 0x0120 */ DMA2_Channel1_IRQHandler,  /* DMA2 Ch1                       */
    /* IRQ57 0x0124 */ DMA2_Channel2_IRQHandler,  /* DMA2 Ch2                       */
    /* IRQ58 0x0128 */ DMA2_Channel3_IRQHandler,  /* DMA2 Ch3                       */
    /* IRQ59 0x012C */ DMA2_Channel4_IRQHandler,  /* DMA2 Ch4 (separate on CL)      */
    /* IRQ60 0x0130 */ DMA2_Channel5_IRQHandler,  /* DMA2 Ch5 (separate on CL)      */
    /* IRQ61 0x0134 */ ETH_IRQHandler,            /* Ethernet global                */
    /* IRQ62 0x0138 */ ETH_WKUP_IRQHandler,       /* Ethernet wakeup via EXTI       */
    /* IRQ63 0x013C */ CAN2_TX_IRQHandler,        /* CAN2 TX                        */
    /* IRQ64 0x0140 */ CAN2_RX0_IRQHandler,       /* CAN2 RX0                       */
    /* IRQ65 0x0144 */ CAN2_RX1_IRQHandler,       /* CAN2 RX1                       */
    /* IRQ66 0x0148 */ CAN2_SCE_IRQHandler,       /* CAN2 SCE                       */
    /* IRQ67 0x014C */ OTG_FS_IRQHandler,         /* USB OTG FS global              */

#elif defined(DENSITY_XL)
    /*
     * XL-density (Table 62).
     * IRQ24–26: TIM1 slots multiplexed with TIM9/10/11.
     * IRQ43–45: TIM8 slots multiplexed with TIM12/13/14.
     * IRQ59: DMA2 Ch4 and Ch5 are COMBINED (unlike CL).
     */
    /* IRQ19 0x008C */ USB_HP_CAN_TX_IRQHandler,          /* USB HP / CAN TX            */
    /* IRQ20 0x0090 */ USB_LP_CAN_RX0_IRQHandler,         /* USB LP / CAN RX0           */
    /* IRQ21 0x0094 */ CAN_RX1_IRQHandler,                /* CAN RX1                    */
    /* IRQ22 0x0098 */ CAN_SCE_IRQHandler,                /* CAN SCE                    */
    /* IRQ23 0x009C */ EXTI9_5_IRQHandler,                /* EXTI Lines 9:5             */
    /* IRQ24 0x00A0 */ TIM1_BRK_TIM9_IRQHandler,          /* TIM1 Break + TIM9 global   */
    /* IRQ25 0x00A4 */ TIM1_UP_TIM10_IRQHandler,          /* TIM1 Update + TIM10 global */
    /* IRQ26 0x00A8 */ TIM1_TRG_COM_TIM11_IRQHandler,     /* TIM1 TRG/COM + TIM11 glbl  */
    /* IRQ27 0x00AC */ TIM1_CC_IRQHandler,                /* TIM1 Capture Compare       */
    /* IRQ28 0x00B0 */ TIM2_IRQHandler,                   /* TIM2 global                */
    /* IRQ29 0x00B4 */ TIM3_IRQHandler,                   /* TIM3 global                */
    /* IRQ30 0x00B8 */ TIM4_IRQHandler,                   /* TIM4 global                */
    /* IRQ31 0x00BC */ I2C1_EV_IRQHandler,                /* I2C1 event                 */
    /* IRQ32 0x00C0 */ I2C1_ER_IRQHandler,                /* I2C1 error                 */
    /* IRQ33 0x00C4 */ I2C2_EV_IRQHandler,                /* I2C2 event                 */
    /* IRQ34 0x00C8 */ I2C2_ER_IRQHandler,                /* I2C2 error                 */
    /* IRQ35 0x00CC */ SPI1_IRQHandler,                   /* SPI1 global                */
    /* IRQ36 0x00D0 */ SPI2_IRQHandler,                   /* SPI2 global                */
    /* IRQ37 0x00D4 */ USART1_IRQHandler,                 /* USART1 global              */
    /* IRQ38 0x00D8 */ USART2_IRQHandler,                 /* USART2 global              */
    /* IRQ39 0x00DC */ USART3_IRQHandler,                 /* USART3 global              */
    /* IRQ40 0x00E0 */ EXTI15_10_IRQHandler,              /* EXTI Lines 15:10           */
    /* IRQ41 0x00E4 */ RTCAlarm_IRQHandler,               /* RTC alarm via EXTI         */
    /* IRQ42 0x00E8 */ USBWakeUp_IRQHandler,              /* USB wakeup via EXTI        */
    /* IRQ43 0x00EC */ TIM8_BRK_TIM12_IRQHandler,         /* TIM8 Break + TIM12 global  */
    /* IRQ44 0x00F0 */ TIM8_UP_TIM13_IRQHandler,          /* TIM8 Update + TIM13 global */
    /* IRQ45 0x00F4 */ TIM8_TRG_COM_TIM14_IRQHandler,     /* TIM8 TRG/COM + TIM14 glbl  */
    /* IRQ46 0x00F8 */ TIM8_CC_IRQHandler,                /* TIM8 Capture Compare       */
    /* IRQ47 0x00FC */ ADC3_IRQHandler,                   /* ADC3 global                */
    /* IRQ48 0x0100 */ FSMC_IRQHandler,                   /* FSMC global                */
    /* IRQ49 0x0104 */ SDIO_IRQHandler,                   /* SDIO global                */
    /* IRQ50 0x0108 */ TIM5_IRQHandler,                   /* TIM5 global                */
    /* IRQ51 0x010C */ SPI3_IRQHandler,                   /* SPI3 global                */
    /* IRQ52 0x0110 */ UART4_IRQHandler,                  /* UART4 global               */
    /* IRQ53 0x0114 */ UART5_IRQHandler,                  /* UART5 global               */
    /* IRQ54 0x0118 */ TIM6_IRQHandler,                   /* TIM6 global                */
    /* IRQ55 0x011C */ TIM7_IRQHandler,                   /* TIM7 global                */
    /* IRQ56 0x0120 */ DMA2_Channel1_IRQHandler,          /* DMA2 Ch1                   */
    /* IRQ57 0x0124 */ DMA2_Channel2_IRQHandler,          /* DMA2 Ch2                   */
    /* IRQ58 0x0128 */ DMA2_Channel3_IRQHandler,          /* DMA2 Ch3                   */
    /* IRQ59 0x012C */ DMA2_Channel4_5_IRQHandler,        /* DMA2 Ch4 & Ch5 (combined)  */

#elif defined(DENSITY_HD)
    /*
     * High-density (Table 63, full 60-entry peripheral table).
     * TIM1 slots are NOT multiplexed (unlike XL).
     * TIM8 slots are NOT multiplexed (unlike XL).
     * IRQ59: DMA2 Ch4 and Ch5 COMBINED (same as XL, different from CL).
     */
    /* IRQ19 0x008C */ USB_HP_CAN_TX_IRQHandler,  /* USB HP / CAN TX                */
    /* IRQ20 0x0090 */ USB_LP_CAN_RX0_IRQHandler, /* USB LP / CAN RX0               */
    /* IRQ21 0x0094 */ CAN_RX1_IRQHandler,        /* CAN RX1                        */
    /* IRQ22 0x0098 */ CAN_SCE_IRQHandler,        /* CAN SCE                        */
    /* IRQ23 0x009C */ EXTI9_5_IRQHandler,        /* EXTI Lines 9:5                 */
    /* IRQ24 0x00A0 */ TIM1_BRK_IRQHandler,       /* TIM1 Break                     */
    /* IRQ25 0x00A4 */ TIM1_UP_IRQHandler,        /* TIM1 Update                    */
    /* IRQ26 0x00A8 */ TIM1_TRG_COM_IRQHandler,   /* TIM1 Trigger & Commutation     */
    /* IRQ27 0x00AC */ TIM1_CC_IRQHandler,        /* TIM1 Capture Compare           */
    /* IRQ28 0x00B0 */ TIM2_IRQHandler,           /* TIM2 global                    */
    /* IRQ29 0x00B4 */ TIM3_IRQHandler,           /* TIM3 global                    */
    /* IRQ30 0x00B8 */ TIM4_IRQHandler,           /* TIM4 global                    */
    /* IRQ31 0x00BC */ I2C1_EV_IRQHandler,        /* I2C1 event                     */
    /* IRQ32 0x00C0 */ I2C1_ER_IRQHandler,        /* I2C1 error                     */
    /* IRQ33 0x00C4 */ I2C2_EV_IRQHandler,        /* I2C2 event                     */
    /* IRQ34 0x00C8 */ I2C2_ER_IRQHandler,        /* I2C2 error                     */
    /* IRQ35 0x00CC */ SPI1_IRQHandler,           /* SPI1 global                    */
    /* IRQ36 0x00D0 */ SPI2_IRQHandler,           /* SPI2 global                    */
    /* IRQ37 0x00D4 */ USART1_IRQHandler,         /* USART1 global                  */
    /* IRQ38 0x00D8 */ USART2_IRQHandler,         /* USART2 global                  */
    /* IRQ39 0x00DC */ USART3_IRQHandler,         /* USART3 global                  */
    /* IRQ40 0x00E0 */ EXTI15_10_IRQHandler,      /* EXTI Lines 15:10               */
    /* IRQ41 0x00E4 */ RTCAlarm_IRQHandler,       /* RTC alarm via EXTI             */
    /* IRQ42 0x00E8 */ USBWakeUp_IRQHandler,      /* USB wakeup via EXTI            */
    /* IRQ43 0x00EC */ TIM8_BRK_IRQHandler,       /* TIM8 Break                     */
    /* IRQ44 0x00F0 */ TIM8_UP_IRQHandler,        /* TIM8 Update                    */
    /* IRQ45 0x00F4 */ TIM8_TRG_COM_IRQHandler,   /* TIM8 Trigger & Commutation     */
    /* IRQ46 0x00F8 */ TIM8_CC_IRQHandler,        /* TIM8 Capture Compare           */
    /* IRQ47 0x00FC */ ADC3_IRQHandler,           /* ADC3 global                    */
    /* IRQ48 0x0100 */ FSMC_IRQHandler,           /* FSMC global                    */
    /* IRQ49 0x0104 */ SDIO_IRQHandler,           /* SDIO global                    */
    /* IRQ50 0x0108 */ TIM5_IRQHandler,           /* TIM5 global                    */
    /* IRQ51 0x010C */ SPI3_IRQHandler,           /* SPI3 global                    */
    /* IRQ52 0x0110 */ UART4_IRQHandler,          /* UART4 global                   */
    /* IRQ53 0x0114 */ UART5_IRQHandler,          /* UART5 global                   */
    /* IRQ54 0x0118 */ TIM6_IRQHandler,           /* TIM6 global                    */
    /* IRQ55 0x011C */ TIM7_IRQHandler,           /* TIM7 global                    */
    /* IRQ56 0x0120 */ DMA2_Channel1_IRQHandler,  /* DMA2 Ch1                       */
    /* IRQ57 0x0124 */ DMA2_Channel2_IRQHandler,  /* DMA2 Ch2                       */
    /* IRQ58 0x0128 */ DMA2_Channel3_IRQHandler,  /* DMA2 Ch3                       */
    /* IRQ59 0x012C */ DMA2_Channel4_5_IRQHandler,/* DMA2 Ch4 & Ch5 (combined)      */

#else /* DENSITY_LD and DENSITY_MD (Table 63, truncated at IRQ42) */
    /*
     * Low- and medium-density (Table 63, IRQ0–42 only).
     * TIM8, ADC3, FSMC, SDIO, and DMA2 are absent on these parts.
     * Slots for TIM4/I2C2/USART3 are present in the table even on LD
     * (those peripherals are simply not wired on the silicon).
     */
    /* IRQ19 0x008C */ USB_HP_CAN_TX_IRQHandler,  /* USB HP / CAN TX                */
    /* IRQ20 0x0090 */ USB_LP_CAN_RX0_IRQHandler, /* USB LP / CAN RX0               */
    /* IRQ21 0x0094 */ CAN_RX1_IRQHandler,        /* CAN RX1                        */
    /* IRQ22 0x0098 */ CAN_SCE_IRQHandler,        /* CAN SCE                        */
    /* IRQ23 0x009C */ EXTI9_5_IRQHandler,        /* EXTI Lines 9:5                 */
    /* IRQ24 0x00A0 */ TIM1_BRK_IRQHandler,       /* TIM1 Break                     */
    /* IRQ25 0x00A4 */ TIM1_UP_IRQHandler,        /* TIM1 Update                    */
    /* IRQ26 0x00A8 */ TIM1_TRG_COM_IRQHandler,   /* TIM1 Trigger & Commutation     */
    /* IRQ27 0x00AC */ TIM1_CC_IRQHandler,        /* TIM1 Capture Compare           */
    /* IRQ28 0x00B0 */ TIM2_IRQHandler,           /* TIM2 global                    */
    /* IRQ29 0x00B4 */ TIM3_IRQHandler,           /* TIM3 global                    */
    /* IRQ30 0x00B8 */ TIM4_IRQHandler,           /* TIM4 global (slot NC on LD)    */
    /* IRQ31 0x00BC */ I2C1_EV_IRQHandler,        /* I2C1 event                     */
    /* IRQ32 0x00C0 */ I2C1_ER_IRQHandler,        /* I2C1 error                     */
    /* IRQ33 0x00C4 */ I2C2_EV_IRQHandler,        /* I2C2 event (slot NC on LD)     */
    /* IRQ34 0x00C8 */ I2C2_ER_IRQHandler,        /* I2C2 error (slot NC on LD)     */
    /* IRQ35 0x00CC */ SPI1_IRQHandler,           /* SPI1 global                    */
    /* IRQ36 0x00D0 */ SPI2_IRQHandler,           /* SPI2 global                    */
    /* IRQ37 0x00D4 */ USART1_IRQHandler,         /* USART1 global                  */
    /* IRQ38 0x00D8 */ USART2_IRQHandler,         /* USART2 global                  */
    /* IRQ39 0x00DC */ USART3_IRQHandler,         /* USART3 global (slot NC on LD)  */
    /* IRQ40 0x00E0 */ EXTI15_10_IRQHandler,      /* EXTI Lines 15:10               */
    /* IRQ41 0x00E4 */ RTCAlarm_IRQHandler,       /* RTC alarm via EXTI             */
    /* IRQ42 0x00E8 */ USBWakeUp_IRQHandler,      /* USB wakeup via EXTI            */
    /* IRQ43–59: not present on LD/MD — table ends here                           */
#endif
};


void Reset_Handler(void)
{
    /* Copy initialised data section from Flash (LMA) to SRAM (VMA) */
    uint32_t *src = &_etext;
    uint32_t *dst = &_sdata;

    while (dst < &_edata)
    {
        *dst++ = *src++;
    }

    /* Zero-initialise the BSS section */
    dst = &_sbss;
    while (dst < &_ebss)
    {
        *dst++ = 0U;
    }

    /* Branch to application */
    main();

    /* main() must never return for a bare-metal target */
    while (1) {}
}


static void Default_Handler(void)
{
    while (1) {}
}
#include <stdint.h>


#if defined(MCU_F103x4) || defined(MCU_F103x6)
  #define DENSITY_LD
#elif defined(MCU_F103xC) || defined(MCU_F103xD) || defined(MCU_F103xE)
  #define DENSITY_HD
#elif defined(MCU_F103xF) || defined(MCU_F103xG)
  #define DENSITY_XL
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

void NMI_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void) __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void)__attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)   __attribute__((weak, alias("Default_Handler")));


__attribute__((used, section(".vectors")))
const void* const vector_table[] =
{
    /* ---- Cortex-M3 core ------------------------------------------------- */
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

    // TODO: Complete with the rest of peripheral IRQ handlers (IRQ 0–59, depending on density tier)
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
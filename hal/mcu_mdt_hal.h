#ifndef MCU_MDT_HAL_H
#define MCU_MDT_HAL_H

#if defined(PLATFORM_AVR)
#include "avr/hal_avr.h"
#elif defined(PLATFORM_PIC)
#include "pic/hal_pic.h"
#else
#error "Unsupported PLATFORM"
#endif

#endif // MCU_MDT_HAL_H
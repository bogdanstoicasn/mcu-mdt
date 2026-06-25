#include "mcu_mdt.h"
#include <stdint.h>

#include <avr/io.h>
#include <avr/interrupt.h>

/*
 * MCU-MDT breakpoint demo for ATmega328P @ 16 MHz (poll mode).
 * TIMER1 ticks every 4 s; the main loop bumps demo_counter then hits
 * MDT_BREAKPOINT(0). Arm slot 0 to halt there and step with NEXT.
 *
 * PC tool:
 *   python3 mcu_mdt.py build/atmega328p/build_info.yaml
 *   ping
 *   read_mem ram demo_counter 4    # climbs every 4 s
 *   breakpoint 0 enabled           # halt at next step
 *   read_mem ram demo_counter 4    # frozen while halted
 *   breakpoint 0 next              # step +1, halt again
 *   breakpoint 0 disabled          # run free
 */

volatile uint32_t demo_counter = 0;
static volatile uint8_t tick_flag = 0;

/* TIMER1 CTC, /1024, compare-match every 4 s (62499 @ 16 MHz). */
static void timer1_init(void)
{
    TCCR1A = 0;
    TCCR1B = (1 << WGM12) | (1 << CS12) | (1 << CS10);
    OCR1A  = (uint16_t)((F_CPU / 1024UL) * 4UL - 1UL);
    TIMSK1 = (1 << OCIE1A);
}

ISR(TIMER1_COMPA_vect)
{
    tick_flag = 1;
}

int main(void)
{
    mcu_mdt_init();    /* USART0 + MDT interface, enables interrupts */
    timer1_init();

    for (;;)
    {
        mcu_mdt_poll();
        if (tick_flag)
        {
            tick_flag = 0;
            demo_counter++;
            MDT_BREAKPOINT(0);
        }
    }

    return 0;
}
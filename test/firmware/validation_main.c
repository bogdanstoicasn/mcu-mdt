/* Validation firmware for the simulation tests (test/simulation/): it gives the PC tool things
 * to look at. loop_count changes on every pass, slow_count every 2^14 passes, right before the
 * firmware hits breakpoint 0. quiet_word never changes on its own. narrow8/narrow16 are narrower
 * than the 4 bytes a watchpoint samples, calls is a function-local static (symbol calls.N), and
 * table lives in flash on STM32. Only mcu_mdt.h, so the same file builds for every platform. */
#include "mcu_mdt.h"
#include <stdint.h>

volatile uint32_t loop_count;
volatile uint32_t slow_count;
volatile uint8_t  narrow8;
volatile uint16_t narrow16;
volatile uint32_t quiet_word = 0x11223344u;
volatile uint8_t  scratch[64];
const uint32_t    table[8] = {0xA0A0A0A0u, 1, 2, 3, 4, 5, 6, 0xDEADBEEFu};

int main(void)
{
    static volatile uint32_t calls;
    mcu_mdt_init();
    for (;;) {
        mcu_mdt_poll();
        loop_count++;
        if ((loop_count & 0x3FFFu) == 0) {
            slow_count++;
            narrow8++;
            narrow16 += 3;
            calls += table[loop_count & 7u] & 1u;
            if (quiet_word == 0u) scratch[0]++;   /* keeps both in the image */
            MDT_BREAKPOINT(0);
        }
    }
    return 0;
}

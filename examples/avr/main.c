#include "mcu_mdt.h"

int main(void) {
    // AVR specific initialization code can go here
    static uint8_t var_my __attribute__((aligned(4))) = 0;
    mcu_mdt_init();
    while (1) {
        // Main loopz
        mcu_mdt_poll();
        var_my++;
        //_delay_ms(1000);
        if (var_my == 255) var_my = 0;
    }

    return 0;
}
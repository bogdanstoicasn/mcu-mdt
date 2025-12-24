#include "mcu_mdt.h"
#include <util/delay.h>

int main(void) {
    // AVR specific initialization code can go here

    mcu_mdt_init();
    while (1) {
        // Main loopz
        mcu_mdt_poll();
    }

    return 0;
}
#include "mcu_mdt.h"

int main(void) {
    // AVR specific initialization code can go here
    mcu_mdt_init();
    while (1) {
        // Main loop
        mcu_mdt_poll();
    }

    return 0;
}
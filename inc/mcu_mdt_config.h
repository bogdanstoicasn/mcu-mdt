#ifndef MCU_MDT_CONFIG_H
#define MCU_MDT_CONFIG_H

/* Common UART configuration for all platforms */
#define MDT_UART_BAUDRATE    19200
#define MDT_UART_DATA_BITS   8
#define MDT_UART_STOP_BITS   1
#define MDT_UART_PARITY      0  // 0=None, 1=Even, 2=Odd

/* Buffer sizes */
#define MDT_RX_BUFFER_SIZE   128
#define MDT_TX_BUFFER_SIZE   128

/* Protocol settings */
#define MDT_TIMEOUT_MS       1000

#ifndef F_CPU
    #define F_CPU 16000000UL  // Default CPU frequency
#endif

/* Enum with the memory zones */
typedef enum {
    MDT_MEM_ZONE_SRAM = 0x00,
    MDT_MEM_ZONE_FLASH = 0x01,
    MDT_MEM_ZONE_EEPROM = 0x02
} mdt_mem_zone_t;

#endif // MCU_MDT_CONFIG_H
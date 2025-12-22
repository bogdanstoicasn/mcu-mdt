#ifndef MCU_MDT_CONFIG_H
#define MCU_MDT_CONFIG_H

/* Common UART configuration for all platforms */
#define MDT_UART_BAUDRATE    115200
#define MDT_UART_DATA_BITS   8
#define MDT_UART_STOP_BITS   1
#define MDT_UART_PARITY      0  // 0=None, 1=Even, 2=Odd

/* Buffer sizes */
#define MDT_RX_BUFFER_SIZE   256
#define MDT_TX_BUFFER_SIZE   256

/* Protocol settings */
#define MDT_PACKET_MAX_SIZE  128
#define MDT_TIMEOUT_MS       1000

#ifndef F_CPU
#define F_CPU 16000000UL  // Default CPU frequency
#endif

#endif // MCU_MDT_CONFIG_H
#include "debug_uart.h"

#include <stdio.h>

#include "driver/uart.h"

#define DEBUG_UART_PORT UART_NUM_1
#define DEBUG_UART_BUF_SIZE 256

void debug_uart_init(void) {
#if CONFIG_DEBUG_UART_ENABLE
    uart_config_t config = {
        .baud_rate = CONFIG_DEBUG_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    uart_param_config(DEBUG_UART_PORT, &config);
    uart_set_pin(
        DEBUG_UART_PORT,
        CONFIG_DEBUG_UART_TX_GPIO,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE
    );
    uart_driver_install(DEBUG_UART_PORT, 0, 0, 0, NULL, 0);
#endif
}

int debug_uart_vprintf(const char *fmt, va_list args) {
#if CONFIG_DEBUG_UART_ENABLE
    char buf[DEBUG_UART_BUF_SIZE];
    int len = vsnprintf(buf, sizeof(buf), fmt, args);
    if (len < 0) {
        return len;
    }
    if (len > (int)sizeof(buf)) {
        len = (int)sizeof(buf);
    }
    uart_write_bytes(DEBUG_UART_PORT, buf, len);
    return len;
#else
    (void)fmt;
    (void)args;
    return 0;
#endif
}

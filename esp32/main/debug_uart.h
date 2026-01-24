#pragma once

#include <stdarg.h>

void debug_uart_init(void);
int debug_uart_vprintf(const char *fmt, va_list args);

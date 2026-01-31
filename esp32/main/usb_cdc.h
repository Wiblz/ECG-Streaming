#pragma once

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

void usb_cdc_init(void);
size_t usb_cdc_write_binary(const uint8_t *data, size_t len);
size_t usb_cdc_write_log(const uint8_t *data, size_t len);
size_t usb_cdc_read_binary(uint8_t *dst, size_t max_len, uint32_t timeout_ms);
int usb_cdc_log_vprintf(const char *fmt, va_list args);

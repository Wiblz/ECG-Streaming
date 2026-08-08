#include "usb_cdc.h"

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/stream_buffer.h"
#include "freertos/task.h"

#include "esp_err.h"
#include "esp_log.h"

#include "tinyusb.h"
#include "tinyusb_cdc_acm.h"
#include "tinyusb_default_config.h"
#include "tusb.h"

static const char *TAG = "USB_CDC";

static StreamBufferHandle_t g_bin_rx_stream;

#define CDC_BINARY_PORT TINYUSB_CDC_ACM_0
#define CDC_LOG_PORT    TINYUSB_CDC_ACM_1

#ifndef CONFIG_TINYUSB_CDC_RX_BUFSIZE
#define CONFIG_TINYUSB_CDC_RX_BUFSIZE 512
#endif

#ifndef CONFIG_TINYUSB_CDC_COUNT
#define CONFIG_TINYUSB_CDC_COUNT 1
#endif

#define BIN_RX_STREAM_SIZE (CONFIG_TINYUSB_CDC_RX_BUFSIZE * 4)
#define BIN_RX_TRIGGER     1

#define USB_EP_SIZE 64
#define USB_CONFIG_ID 1

enum {
    ITF_NUM_CDC0 = 0,
    ITF_NUM_CDC0_DATA,
    ITF_NUM_CDC1,
    ITF_NUM_CDC1_DATA,
    ITF_NUM_TOTAL
};

#define USB_DESC_TOTAL_LEN (TUD_CONFIG_DESC_LEN + 2 * TUD_CDC_DESC_LEN)

static const char *cdc_string_descriptor[] = {
    (char[]){0x09, 0x04},  // 0: English (0x0409)
    "ECG Streaming",       // 1: Manufacturer
    "ECG-ESP32",           // 2: Product
    "ECG-ESP32-USB",       // 3: Serial
    "ECG-ESP-DATA",        // 4: CDC0 interface
    "ECG-ESP-LOG",         // 5: CDC1 interface
};

static const uint8_t cdc_configuration_descriptor[] = {
    TUD_CONFIG_DESCRIPTOR(USB_CONFIG_ID, ITF_NUM_TOTAL, 0, USB_DESC_TOTAL_LEN, 0, 100),
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC0, 4, 0x81, 8, 0x02, 0x82, USB_EP_SIZE),
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC1, 5, 0x83, 8, 0x04, 0x84, USB_EP_SIZE),
};


static void usb_cdc_rx_callback(int itf, cdcacm_event_t *event) {
    (void)event;

    if (itf != CDC_BINARY_PORT) {
        return;
    }

    uint8_t buf[CONFIG_TINYUSB_CDC_RX_BUFSIZE];
    size_t rx_size = 0;

    while (tinyusb_cdcacm_read(itf, buf, sizeof(buf), &rx_size) == ESP_OK && rx_size > 0) {
        (void)xStreamBufferSend(g_bin_rx_stream, buf, rx_size, 0);
        rx_size = 0;
    }
}

void usb_cdc_init(void) {
    tinyusb_config_t tusb_cfg = TINYUSB_DEFAULT_CONFIG();
    tusb_cfg.descriptor.device = NULL;
    tusb_cfg.descriptor.full_speed_config = cdc_configuration_descriptor;
    tusb_cfg.descriptor.string = cdc_string_descriptor;
    tusb_cfg.descriptor.string_count = sizeof(cdc_string_descriptor) / sizeof(cdc_string_descriptor[0]);
#if (TUD_OPT_HIGH_SPEED)
    tusb_cfg.descriptor.high_speed_config = cdc_configuration_descriptor;
#endif
    ESP_ERROR_CHECK(tinyusb_driver_install(&tusb_cfg));

    g_bin_rx_stream = xStreamBufferCreate(BIN_RX_STREAM_SIZE, BIN_RX_TRIGGER);
    if (!g_bin_rx_stream) {
        ESP_LOGE(TAG, "Failed to create CDC RX stream");
    }

    tinyusb_config_cdcacm_t acm_cfg = {
        .cdc_port = CDC_BINARY_PORT,
        .callback_rx = &usb_cdc_rx_callback,
        .callback_rx_wanted_char = NULL,
        .callback_line_state_changed = NULL,
        .callback_line_coding_changed = NULL,
    };
    ESP_ERROR_CHECK(tinyusb_cdcacm_init(&acm_cfg));

#if (CONFIG_TINYUSB_CDC_COUNT > 1)
    acm_cfg.cdc_port = CDC_LOG_PORT;
    acm_cfg.callback_rx = NULL;
    ESP_ERROR_CHECK(tinyusb_cdcacm_init(&acm_cfg));
#endif
}

size_t usb_cdc_write_binary(const uint8_t *data, size_t len) {
    if (!data || len == 0) {
        return 0;
    }
    size_t queued = tinyusb_cdcacm_write_queue(CDC_BINARY_PORT, data, len);
    (void)tinyusb_cdcacm_write_flush(CDC_BINARY_PORT, 0);
    return queued;
}

// Once a frame write has started it must complete or the stream tears
// mid-frame, so committed writes get a longer budget than the pre-check.
#define USB_CDC_COMMIT_TIMEOUT_MS 250

static bool cdc_binary_write_all(const uint8_t *data, size_t len) {
    TickType_t start = xTaskGetTickCount();
    size_t written = 0;
    while (written < len) {
        written += tinyusb_cdcacm_write_queue(CDC_BINARY_PORT, data + written, len - written);
        (void)tinyusb_cdcacm_write_flush(CDC_BINARY_PORT, 0);
        if (written < len) {
            if ((TickType_t)(xTaskGetTickCount() - start) >= pdMS_TO_TICKS(USB_CDC_COMMIT_TIMEOUT_MS)) {
                return false;
            }
            vTaskDelay(1);
        }
    }
    return true;
}

bool usb_cdc_write_frame(const uint8_t *prefix, size_t prefix_len,
                         const uint8_t *body, size_t body_len,
                         uint32_t timeout_ms) {
    if (!prefix || prefix_len == 0 || !body || body_len == 0) {
        return false;
    }

    size_t total = prefix_len + body_len;
    // Frames larger than the TX FIFO cannot be reserved up front; require a
    // fully drained FIFO before committing to a chunked write.
    size_t needed = (total <= CFG_TUD_CDC_TX_BUFSIZE) ? total : (size_t)CFG_TUD_CDC_TX_BUFSIZE;

    TickType_t start = xTaskGetTickCount();
    TickType_t timeout_ticks = pdMS_TO_TICKS(timeout_ms);
    while (tud_cdc_n_write_available(CDC_BINARY_PORT) < needed) {
        if ((TickType_t)(xTaskGetTickCount() - start) >= timeout_ticks) {
            return false;
        }
        vTaskDelay(1);
    }

    return cdc_binary_write_all(prefix, prefix_len) &&
           cdc_binary_write_all(body, body_len);
}

size_t usb_cdc_write_log(const uint8_t *data, size_t len) {
    if (!data || len == 0) {
        return 0;
    }
    tinyusb_cdcacm_write_queue(CDC_LOG_PORT, data, len);
    (void)tinyusb_cdcacm_write_flush(CDC_LOG_PORT, 0);
    return len;
}

size_t usb_cdc_read_binary(uint8_t *dst, size_t max_len, uint32_t timeout_ms) {
    if (!dst || max_len == 0 || !g_bin_rx_stream) {
        return 0;
    }
    TickType_t ticks = pdMS_TO_TICKS(timeout_ms);
    return xStreamBufferReceive(g_bin_rx_stream, dst, max_len, ticks);
}

int usb_cdc_log_vprintf(const char *fmt, va_list args) {
    char buf[256];
    int len = vsnprintf(buf, sizeof(buf), fmt, args);
    if (len <= 0) {
        return len;
    }
    if ((size_t)len > sizeof(buf)) {
        len = (int)sizeof(buf);
    }
    usb_cdc_write_log((const uint8_t *)buf, (size_t)len);
    return len;
}

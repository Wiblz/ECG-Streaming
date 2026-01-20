#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"

#include "ble_polar.h"
#include "config_store.h"
#include "state.h"
#include "usb_provision.h"

void app_main(void) {
#if BINARY_OUTPUT_MODE
    esp_log_level_set("*", ESP_LOG_NONE);
#else
    esp_log_level_set("*", ESP_LOG_INFO);
    esp_log_level_set("NimBLE", ESP_LOG_WARN);
#endif

    config_store_init();

#if !BINARY_OUTPUT_MODE
    ESP_LOGI("H10_COMBINED", "Polar H10 ECG + ACC Streamer");
    if (has_target_device()) {
        ESP_LOGI("H10_COMBINED", "Target/Device ID: %s", g_target_device_name);
    } else {
        ESP_LOGI("H10_COMBINED", "Target/Device ID: <unassigned>");
    }
    ESP_LOGI("H10_COMBINED", "ECG: %d Hz | ACC: %d Hz", g_ecg_sample_rate_hz, g_acc_sample_rate_hz);
    ESP_LOGI("H10_COMBINED", "Mode: HUMAN READABLE");
    ESP_LOGI("H10_COMBINED", "");
#endif

    ble_init();

    xTaskCreate(watchdog_task, "watchdog", 4096, NULL, 5, NULL);
    xTaskCreate(usb_identity_task, "usb_id", 4096, NULL, 4, NULL);
    xTaskCreate(usb_rx_task, "usb_rx", 4096, NULL, 4, NULL);
}

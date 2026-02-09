#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "config_store.h"
#include "state.h"
#include "usb_cdc.h"
#include "usb_output.h"
#include "usb_provision.h"
#include "usb_transport.h"
#include "ble_polar.h"
#include "led_status.h"

static const char *TAG = "H10_COMBINED";

// ============================================================================
// Watchdog Task - Status every second
// ============================================================================

static void watchdog_task(void *param) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        
        // Start ACC after first ECG data arrives (per link)
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            polar_link_t *link = &g_links[i];
            if (
                link->connected
                && link->ecg_started
                && !link->acc_started
                && link->ecg_packet_count >= 2
                && link->acc_sample_rate_hz > 0
            ) {
                ESP_LOGI(TAG, "Link %d ECG streaming confirmed, starting ACC...", i);
                ble_schedule_start_acc();
            }
        }
        
        // Calculate rates
        float elapsed_sec = 0;
        float ecg_rate = 0;
        float acc_rate = 0;
        
        TickType_t first_time = 0;
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            if (g_links[i].first_sample_time > 0) {
                first_time = g_links[i].first_sample_time;
                break;
            }
        }
        if (first_time > 0) {
            TickType_t elapsed_ticks = xTaskGetTickCount() - first_time;
            elapsed_sec = elapsed_ticks * portTICK_PERIOD_MS / 1000.0f;
            
            if (elapsed_sec > 0) {
                uint32_t total_ecg = 0;
                uint32_t total_acc = 0;
                for (int i = 0; i < MAX_POLAR_LINKS; i++) {
                    total_ecg += g_links[i].total_ecg_samples;
                    total_acc += g_links[i].total_acc_samples;
                }
                ecg_rate = total_ecg / elapsed_sec;
                acc_rate = total_acc / elapsed_sec;
            }
        }
        
        // Print status every second
        bool any_connected = false;
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            if (g_links[i].connected) {
                any_connected = true;
                break;
            }
        }
        if (any_connected) {
            ESP_LOGI(TAG,
                     "Status: ECG %.1f Hz | ACC %.1f Hz",
                     ecg_rate, acc_rate);
        }
    }
}

// ============================================================================
// BLE Initialization
// ============================================================================

// ============================================================================
// Main
// ============================================================================

void app_main(void) {
    g_links[0].target_device_name[0] = '\0';

    config_store_init();
    usb_cdc_init();
#if CONFIG_LOG_STREAM_USB_CDC
    esp_log_set_vprintf(usb_cdc_log_vprintf);
#endif
    esp_log_level_set("*", ESP_LOG_INFO);
    esp_log_level_set("NimBLE", ESP_LOG_WARN);
    usb_transport_init();
    led_status_init();

    ble_init();
    
    xTaskCreate(watchdog_task, "watchdog", 4096, NULL, 5, NULL);
    xTaskCreate(usb_identity_task, "usb_id", 4096, NULL, 4, NULL);
    xTaskCreate(usb_rx_task, "usb_rx", 4096, NULL, 4, NULL);
}

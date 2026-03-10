#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_system.h"
#include "config_store.h"
#include "state.h"
#include "usb_cdc.h"
#include "usb_output.h"
#include "usb_provision.h"
#include "usb_transport.h"
#include "ble_polar.h"
#include "led_status.h"

static const char *TAG = "H10_COMBINED";

static const char *reset_reason_to_str(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_UNKNOWN:
            return "unknown";
        case ESP_RST_POWERON:
            return "poweron";
        case ESP_RST_EXT:
            return "external";
        case ESP_RST_SW:
            return "software";
        case ESP_RST_PANIC:
            return "panic";
        case ESP_RST_INT_WDT:
            return "int_wdt";
        case ESP_RST_TASK_WDT:
            return "task_wdt";
        case ESP_RST_WDT:
            return "wdt";
        case ESP_RST_DEEPSLEEP:
            return "deepsleep";
        case ESP_RST_BROWNOUT:
            return "brownout";
        case ESP_RST_SDIO:
            return "sdio";
        case ESP_RST_USB:
            return "usb";
        case ESP_RST_JTAG:
            return "jtag";
        case ESP_RST_EFUSE:
            return "efuse";
        case ESP_RST_PWR_GLITCH:
            return "power_glitch";
        case ESP_RST_CPU_LOCKUP:
            return "cpu_lockup";
        default:
            return "other";
    }
}

// ============================================================================
// Watchdog Task - Status every second
// ============================================================================

static void watchdog_task(void *param) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        
        // Start ACC after first ECG data arrives
        if (
            g_connected
            && g_ecg_started
            && !g_acc_started
            && g_ecg_packet_count >= 2
            && g_acc_sample_rate_hz > 0
        ) {
            ESP_LOGI(TAG, "ECG streaming confirmed, starting ACC...");
            ble_schedule_start_acc();
            // Note: g_acc_started is set to true in pmd_start_acc() after START command is sent
        }
        
        // Calculate rates
        float elapsed_sec = 0;
        float ecg_rate = 0;
        float acc_rate = 0;
        
        if (g_first_sample_time > 0) {
            TickType_t elapsed_ticks = xTaskGetTickCount() - g_first_sample_time;
            elapsed_sec = elapsed_ticks * portTICK_PERIOD_MS / 1000.0f;
            
            if (elapsed_sec > 0) {
                ecg_rate = g_total_ecg_samples / elapsed_sec;
                acc_rate = g_total_acc_samples / elapsed_sec;
            }
        }
        
        // Print status every second
        if (g_connected) {
            ESP_LOGI(TAG, "Status: ECG %lu pkt/%lu smp (%.1f Hz) | ACC %lu pkt/%lu smp (%.1f Hz) | Buf: ECG %d ACC %d", 
                     g_ecg_packet_count, g_total_ecg_samples, ecg_rate,
                     g_acc_packet_count, g_total_acc_samples, acc_rate,
                     g_ecg_count, g_acc_count);
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
    g_target_device_name[0] = '\0';
    g_device_id[0] = '\0';

    config_store_init();
    usb_cdc_init();
#if CONFIG_LOG_STREAM_USB_CDC
    esp_log_set_vprintf(usb_cdc_log_vprintf);
#endif
    esp_log_level_set("*", ESP_LOG_INFO);
    esp_log_level_set("NimBLE", ESP_LOG_WARN);
    esp_reset_reason_t reset_reason = esp_reset_reason();
    ESP_LOGI(
        TAG,
        "Booting app=%s proto=%d reset_reason=%s (%d)",
        CONFIG_ECG_APP_VERSION,
        CONFIG_ECG_PROTOCOL_VERSION,
        reset_reason_to_str(reset_reason),
        (int)reset_reason
    );
    usb_transport_init();
    led_status_init();

    ble_init();
    
    xTaskCreate(watchdog_task, "watchdog", 4096, NULL, 5, NULL);
    xTaskCreate(usb_identity_task, "usb_id", 4096, NULL, 4, NULL);
    xTaskCreate(usb_rx_task, "usb_rx", 4096, NULL, 4, NULL);
}

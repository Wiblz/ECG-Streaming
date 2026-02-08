#include "usb_provision.h"

#include <string.h>

#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "host/ble_gap.h"

#include "ble_polar.h"
#include "config_store.h"
#include "common.pb.h"
#include "esp_collector.pb.h"
#include "state.h"
#include "usb_transport.h"

static const char *TAG = "usb_provision";

static void send_usb_device_info(void) {
    ecg_streaming_UsbDeviceInfo info = ecg_streaming_UsbDeviceInfo_init_zero;
    ecg_streaming_EspMessage msg = ecg_streaming_EspMessage_init_zero;

    strlcpy(info.esp_id, g_esp_id, sizeof(info.esp_id));
    strlcpy(info.firmware_version, esp_get_idf_version(), sizeof(info.firmware_version));
    strlcpy(info.current_target, g_target_device_name, sizeof(info.current_target));
    info.config_required = g_config_required;
    info.polar_connected = g_connected;
    info.polar_status = g_connected ? ecg_streaming_DeviceStatus_DEVICE_STATUS_STREAMING :
                                      ecg_streaming_DeviceStatus_DEVICE_STATUS_DISCONNECTED;

    msg.which_message = ecg_streaming_EspMessage_device_info_tag;
    msg.message.device_info = info;

    usb_send_esp_message(&msg);
}

static void send_usb_config_ack(bool accepted, const char *message, const char *target) {
    ecg_streaming_UsbConfigAck ack = ecg_streaming_UsbConfigAck_init_zero;
    ecg_streaming_EspMessage msg = ecg_streaming_EspMessage_init_zero;

    strlcpy(ack.esp_id, g_esp_id, sizeof(ack.esp_id));
    ack.accepted = accepted;
    if (message) {
        strlcpy(ack.message, message, sizeof(ack.message));
    }
    if (target) {
        strlcpy(ack.target_device_id, target, sizeof(ack.target_device_id));
    }

    msg.which_message = ecg_streaming_EspMessage_config_ack_tag;
    msg.message.config_ack = ack;

    usb_send_esp_message(&msg);
}

static void apply_usb_config(const ecg_streaming_UsbConfig *cfg) {
    bool changed = false;
    int prev_ecg_rate = g_ecg_sample_rate_hz;
    int prev_acc_rate = g_acc_sample_rate_hz;

    if (cfg->target_device_id[0] != '\0' &&
        strcmp(cfg->target_device_id, g_target_device_name) != 0) {
        strlcpy(g_target_device_name, cfg->target_device_id, sizeof(g_target_device_name));
        changed = true;
    }

    if (cfg->ecg_sample_rate >= 0) {
        g_ecg_sample_rate_hz = cfg->ecg_sample_rate;
    }
    if (cfg->acc_sample_rate >= 0) {
        g_acc_sample_rate_hz = cfg->acc_sample_rate;
    }

    if (g_ecg_sample_rate_hz != prev_ecg_rate || g_acc_sample_rate_hz != prev_acc_rate) {
        changed = true;
    }

    apply_runtime_config();

#ifdef CONFIG_ALLOW_USB_CONFIG_PERSIST
    if (cfg->persist) {
        persist_usb_config_to_nvs();
    }
#else
    if (cfg->persist) {
        ESP_LOGW(TAG, "Config persist requested but CONFIG_ALLOW_USB_CONFIG_PERSIST disabled");
    }
#endif

    g_config_required = false;

    if (changed) {
        if (g_connected) {
            ble_gap_terminate(g_conn_handle, BLE_ERR_REM_USER_CONN_TERM);
        } else {
            ble_gap_disc_cancel();
            start_scan();
        }
        return;
    }

    if (g_connected && !g_ecg_started && g_ecg_sample_rate_hz > 0) {
        pmd_start_ecg(g_conn_handle, g_pmd_ctrl_handle);
    }
    if (g_connected && !g_acc_started && g_acc_sample_rate_hz > 0) {
        pmd_start_acc(g_conn_handle, g_pmd_ctrl_handle);
    }
}

void usb_identity_task(void *param) {
    while (1) {
        send_usb_device_info();
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

void usb_rx_task(void *param) {
    ecg_streaming_CollectorToEspMessage msg = ecg_streaming_CollectorToEspMessage_init_zero;
    while (1) {
        if (!usb_receive_collector_to_esp_message(&msg)) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        if (msg.which_message == ecg_streaming_CollectorToEspMessage_config_tag) {
            ecg_streaming_UsbConfig *cfg = &msg.message.config;
            if (cfg->esp_id[0] != '\0' && strcmp(cfg->esp_id, g_esp_id) != 0) {
                continue;
            }
            apply_usb_config(cfg);
            send_usb_config_ack(true, "config applied", cfg->target_device_id);
        }
    }
}

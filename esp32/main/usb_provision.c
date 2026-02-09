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
    info.config_required = g_config_required;
    bool any_connected = false;
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].connected) {
            any_connected = true;
            break;
        }
    }
    info.polar_connected = any_connected;
    info.polar_status = any_connected ? ecg_streaming_DeviceStatus_DEVICE_STATUS_STREAMING :
                                      ecg_streaming_DeviceStatus_DEVICE_STATUS_DISCONNECTED;

    info.targets_count = 0;
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (!g_links[i].in_use && !g_links[i].connected) {
            continue;
        }
        ecg_streaming_UsbTargetInfo *target = &info.targets[info.targets_count++];
        target->target_device_id[0] = '\0';
        if (g_links[i].target_device_name[0] != '\0') {
            strlcpy(target->target_device_id, g_links[i].target_device_name,
                    sizeof(target->target_device_id));
        }
        target->polar_connected = g_links[i].connected;
        target->polar_status = g_links[i].connected
                                   ? ecg_streaming_DeviceStatus_DEVICE_STATUS_STREAMING
                                   : ecg_streaming_DeviceStatus_DEVICE_STATUS_DISCONNECTED;
        target->ecg_sample_rate = g_links[i].ecg_sample_rate_hz;
        target->acc_sample_rate = g_links[i].acc_sample_rate_hz;
    }

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
    int prev_ecg_rate[MAX_POLAR_LINKS];
    int prev_acc_rate[MAX_POLAR_LINKS];
    char prev_targets[MAX_POLAR_LINKS][DEVICE_ID_MAX_LEN];
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        prev_ecg_rate[i] = g_links[i].ecg_sample_rate_hz;
        prev_acc_rate[i] = g_links[i].acc_sample_rate_hz;
        strlcpy(prev_targets[i], g_links[i].target_device_name, sizeof(prev_targets[i]));
    }

    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (i < (int)cfg->targets_count) {
            const ecg_streaming_UsbTargetConfig *target = &cfg->targets[i];
            if (target->target_device_id[0] != '\0' &&
                strcmp(target->target_device_id, g_links[i].target_device_name) != 0) {
                strlcpy(g_links[i].target_device_name, target->target_device_id,
                        sizeof(g_links[i].target_device_name));
                changed = true;
            }
            if (target->ecg_sample_rate >= 0) {
                g_links[i].ecg_sample_rate_hz = target->ecg_sample_rate;
            }
            if (target->acc_sample_rate >= 0) {
                g_links[i].acc_sample_rate_hz = target->acc_sample_rate;
            }
            g_links[i].in_use = g_links[i].target_device_name[0] != '\0';
        } else {
            if (g_links[i].target_device_name[0] != '\0') {
                g_links[i].target_device_name[0] = '\0';
                g_links[i].in_use = false;
                changed = true;
            }
        }
    }

    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].ecg_sample_rate_hz != prev_ecg_rate[i]
            || g_links[i].acc_sample_rate_hz != prev_acc_rate[i]
            || strcmp(g_links[i].target_device_name, prev_targets[i]) != 0) {
            changed = true;
            break;
        }
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
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            if (g_links[i].connected) {
                ble_gap_terminate(g_links[i].conn_handle, BLE_ERR_REM_USER_CONN_TERM);
            }
        }
        ble_gap_disc_cancel();
        start_scan();
        return;
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
            const char *target_id = NULL;
            if (cfg->targets_count > 0) {
                target_id = cfg->targets[0].target_device_id;
            }
            send_usb_config_ack(true, "config applied", target_id);
        }
    }
}

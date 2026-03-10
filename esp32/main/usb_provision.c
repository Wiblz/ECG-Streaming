#include "usb_provision.h"

#include <stdlib.h>
#include <string.h>

#include "esp_log.h"
#include "esp_system.h"
#include "sdkconfig.h"
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
    strlcpy(info.app_version, CONFIG_ECG_APP_VERSION, sizeof(info.app_version));
    strlcpy(info.idf_version, esp_get_idf_version(), sizeof(info.idf_version));
    info.protocol_version = CONFIG_ECG_PROTOCOL_VERSION;
    strlcpy(info.current_target, g_target_device_name, sizeof(info.current_target));
    info.config_required = g_config_required;
    info.polar_connected = g_connected;
    info.polar_status = g_connected ? ecg_streaming_DeviceStatus_DEVICE_STATUS_STREAMING :
                                      ecg_streaming_DeviceStatus_DEVICE_STATUS_DISCONNECTED;
    info.scanner_active = g_scanner_active;
    info.scanner_request_id = g_scanner_request_id;

    msg.which_message = ecg_streaming_EspMessage_device_info_tag;
    msg.message.device_info = info;

    usb_send_esp_message(&msg);
}

void usb_send_ble_scan_result(
    uint32_t request_id,
    const ecg_streaming_BleScanSighting *sightings,
    size_t sighting_count,
    uint32_t duration_ms
) {
    ecg_streaming_EspDiscoveryMessage *msg = calloc(1, sizeof(*msg));
    if (!msg) {
        ESP_LOGE(TAG, "Failed to allocate scan result message");
        return;
    }

    *msg = (ecg_streaming_EspDiscoveryMessage)ecg_streaming_EspDiscoveryMessage_init_zero;
    msg->which_message = ecg_streaming_EspDiscoveryMessage_ble_scan_result_tag;
    msg->message.ble_scan_result.request_id = request_id;
    msg->message.ble_scan_result.duration_ms = duration_ms;
    strlcpy(msg->message.ble_scan_result.esp_id, g_esp_id, sizeof(msg->message.ble_scan_result.esp_id));

    size_t max_sightings = sizeof(msg->message.ble_scan_result.sightings)
        / sizeof(msg->message.ble_scan_result.sightings[0]);
    if (sighting_count > max_sightings) {
        sighting_count = max_sightings;
    }
    for (size_t i = 0; i < sighting_count; i++) {
        msg->message.ble_scan_result.sightings[i] = sightings[i];
    }
    msg->message.ble_scan_result.sightings_count = (pb_size_t)sighting_count;

    (void)usb_send_esp_discovery_message(msg);
    free(msg);
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
    g_scanner_active = false;

    ble_apply_updated_config(changed);
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
            continue;
        }
        if (msg.which_message == ecg_streaming_CollectorToEspMessage_start_ble_scan_tag) {
            ecg_streaming_StartBleScan *scan = &msg.message.start_ble_scan;
            if (scan->esp_id[0] != '\0' && strcmp(scan->esp_id, g_esp_id) != 0) {
                continue;
            }
            ble_start_scan_request(scan->request_id, scan->duration_ms, scan->name_prefix);
        }
    }
}

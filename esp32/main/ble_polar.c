#include "ble_polar.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "host/ble_gatt.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "os/os_mbuf.h"
#include "pb.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include "config_store.h"
#include "ecg_streaming.pb.h"
#include "state.h"
#include "usb_transport.h"

static const char *TAG = "H10_COMBINED";

// Polar H10 BLE UUIDs
static const ble_uuid128_t UUID_PMD_SVC  = BLE_UUID128_INIT(
    0xC8, 0x5F, 0x8D, 0x2D, 0xCD, 0x8A, 0xAD, 0x1C,
    0x87, 0xF3, 0xE7, 0x02, 0x80, 0x5C, 0x00, 0xFB);
static const ble_uuid128_t UUID_PMD_CTRL = BLE_UUID128_INIT(
    0xC8, 0x5F, 0x8D, 0x2D, 0xCD, 0x8A, 0xAD, 0x1C,
    0x87, 0xF3, 0xE7, 0x02, 0x81, 0x5C, 0x00, 0xFB);
static const ble_uuid128_t UUID_PMD_DATA = BLE_UUID128_INIT(
    0xC8, 0x5F, 0x8D, 0x2D, 0xCD, 0x8A, 0xAD, 0x1C,
    0x87, 0xF3, 0xE7, 0x02, 0x82, 0x5C, 0x00, 0xFB);

// PMD Measurement Types
#define PMD_TYPE_ECG 0x00
#define PMD_TYPE_ACC 0x02

static int gap_event(struct ble_gap_event *event, void *arg);

static void addr_to_str(const ble_addr_t *addr, char *out, size_t out_len) {
    snprintf(out, out_len, "%02x:%02x:%02x:%02x:%02x:%02x",
             addr->val[5], addr->val[4], addr->val[3],
             addr->val[2], addr->val[1], addr->val[0]);
}

static bool parse_adv_name(const uint8_t *adv_data, int adv_len, char *name_out, int name_out_len) {
    int pos = 0;
    while (pos < adv_len) {
        uint8_t length = adv_data[pos];
        if (length == 0 || pos + length >= adv_len) {
            break;
        }

        uint8_t type = adv_data[pos + 1];

        if (type == 0x09 || type == 0x08) {
            uint8_t name_len = length - 1;

            size_t copy_len = name_len < (name_out_len - 1) ? name_len : (name_out_len - 1);
            memcpy(name_out, &adv_data[pos + 2], copy_len);
            name_out[copy_len] = '\0';

            return true;
        }

        pos += length + 1;
    }

    return false;
}

static void output_ecg_binary(void) {
    if (g_ecg_count == 0) return;

#if BINARY_OUTPUT_MODE
    ecg_streaming_ECGSampleBatch ecg_batch = ecg_streaming_ECGSampleBatch_init_zero;
    ecg_streaming_CollectorMessage collector_msg = ecg_streaming_CollectorMessage_init_zero;

    strlcpy(ecg_batch.device_id, g_device_id, sizeof(ecg_batch.device_id));
    ecg_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    ecg_batch.samples_count = (pb_size_t)g_ecg_count;

    for (int i = 0; i < g_ecg_count; i++) {
        ecg_streaming_ECGSample *sample = &ecg_batch.samples[i];
        sample->device_timestamp_us = (double)(g_ecg_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->raw_value = g_ecg_buffer[i].value_uv;
        sample->sample_rate = g_ecg_sample_rate_hz;
    }

    collector_msg.which_message = ecg_streaming_CollectorMessage_ecg_batch_tag;
    collector_msg.message.ecg_batch = ecg_batch;

    if (!usb_send_collector_message(&collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ECG batch");
    }
#endif

    g_ecg_count = 0;
}

static void output_acc_binary(void) {
    if (g_acc_count == 0) return;

#if BINARY_OUTPUT_MODE
    ecg_streaming_AccelerometerSampleBatch acc_batch =
        ecg_streaming_AccelerometerSampleBatch_init_zero;
    ecg_streaming_CollectorMessage collector_msg = ecg_streaming_CollectorMessage_init_zero;

    strlcpy(acc_batch.device_id, g_device_id, sizeof(acc_batch.device_id));
    acc_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    acc_batch.samples_count = (pb_size_t)g_acc_count;

    for (int i = 0; i < g_acc_count; i++) {
        ecg_streaming_AccelerometerSample *sample = &acc_batch.samples[i];
        sample->device_timestamp_us = (double)(g_acc_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->x = (float)g_acc_buffer[i].x_mg / 1000.0f;
        sample->y = (float)g_acc_buffer[i].y_mg / 1000.0f;
        sample->z = (float)g_acc_buffer[i].z_mg / 1000.0f;
        sample->sample_rate = g_acc_sample_rate_hz;
    }

    collector_msg.which_message = ecg_streaming_CollectorMessage_acc_batch_tag;
    collector_msg.message.acc_batch = acc_batch;

    if (!usb_send_collector_message(&collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ACC batch");
    }
#endif

    g_acc_count = 0;
}

static void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle) {
    uint16_t ecg_rate = (uint16_t)g_ecg_sample_rate_hz;
    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ECG};

    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_simple, sizeof(cmd_simple),
                                  NULL, "START_ECG_SIMPLE");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ECG_SIMPLE failed: %d", rc);
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(1000));

    uint8_t cmd_full[10] = {
        0x02, 0x00,
        0x00, 0x01, (uint8_t)(ecg_rate & 0xFF), (uint8_t)((ecg_rate >> 8) & 0xFF),
        0x01, 0x01, 0x0E, 0x00
    };

    rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                              cmd_full, sizeof(cmd_full),
                              NULL, "START_ECG_FULL");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ECG_FULL failed: %d", rc);
        return;
    }

    g_ecg_started = true;
}

static void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle) {
    uint16_t acc_rate = (uint16_t)g_acc_sample_rate_hz;
    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ACC};

    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_simple, sizeof(cmd_simple),
                                  NULL, "START_ACC_SIMPLE");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ACC_SIMPLE failed: %d", rc);
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(1000));

    uint8_t cmd_full[14] = {
        0x02, 0x02,
        0x00, 0x01, (uint8_t)(acc_rate & 0xFF), (uint8_t)((acc_rate >> 8) & 0xFF),
        0x01, 0x01, 0x10, 0x00,
        0x02, 0x01, 0x02, 0x00
    };

    rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                              cmd_full, sizeof(cmd_full),
                              NULL, "START_ACC_FULL");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ACC_FULL failed: %d", rc);
        return;
    }

    g_acc_started = true;
}

static void parse_pmd_response(uint8_t *data, int len) {
    g_notification_count++;

    if (len < 2) {
        return;
    }

    uint8_t type = data[0];
    uint64_t timestamp_ns = ((uint64_t)data[1] |
                            ((uint64_t)data[2] << 8) |
                            ((uint64_t)data[3] << 16) |
                            ((uint64_t)data[4] << 24) |
                            ((uint64_t)data[5] << 32) |
                            ((uint64_t)data[6] << 40) |
                            ((uint64_t)data[7] << 48) |
                            ((uint64_t)data[8] << 56));

    if (type == PMD_TYPE_ECG) {
        int num_samples = (len - 10) / 3;
        for (int i = 0; i < num_samples && g_ecg_count < MAX_ECG_SAMPLES; i++) {
            int idx = 10 + i * 3;
            int32_t sample = (int32_t)(data[idx] | (data[idx + 1] << 8) | (data[idx + 2] << 16));
            if (sample & 0x800000) {
                sample |= 0xFF000000;
            }
            g_ecg_buffer[g_ecg_count].timestamp_ns =
                timestamp_ns + ((int64_t)i - (int64_t)num_samples + 1) *
                1000000000LL / g_ecg_sample_rate_hz;
            g_ecg_buffer[g_ecg_count].value_uv = sample;
            g_ecg_count++;
        }

        g_ecg_packet_count++;
        g_total_ecg_samples += num_samples;

        if (g_first_sample_time == 0) {
            g_first_sample_time = xTaskGetTickCount();
        }

        if (g_ecg_count >= g_ecg_batch_size) {
            output_ecg_binary();
        }
    } else if (type == PMD_TYPE_ACC) {
        int num_acc_samples = (len - 10) / 6;
        for (int i = 0; i < num_acc_samples && g_acc_count < MAX_ACC_SAMPLES; i++) {
            int idx = 10 + i * 6;
            int16_t x = (int16_t)(data[idx] | (data[idx + 1] << 8));
            int16_t y = (int16_t)(data[idx + 2] | (data[idx + 3] << 8));
            int16_t z = (int16_t)(data[idx + 4] | (data[idx + 5] << 8));

            g_acc_buffer[g_acc_count].timestamp_ns =
                timestamp_ns + ((int64_t)i - (int64_t)num_acc_samples + 1) *
                1000000000LL / g_acc_sample_rate_hz;
            g_acc_buffer[g_acc_count].x_mg = x;
            g_acc_buffer[g_acc_count].y_mg = y;
            g_acc_buffer[g_acc_count].z_mg = z;
            g_acc_count++;
        }

        g_acc_packet_count++;
        g_total_acc_samples += num_acc_samples;

        if (g_first_sample_time == 0) {
            g_first_sample_time = xTaskGetTickCount();
        }

        if (g_acc_count >= g_acc_batch_size) {
            output_acc_binary();
        }
    }
}

static int dsc_disc_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                       uint16_t chr_val_handle, const struct ble_gatt_dsc *dsc, void *arg) {
    if (error->status == BLE_HS_EDONE) {
        if (g_pmd_cccd_handle) {
            uint8_t notify_on[2] = {0x01, 0x00};
            int rc = ble_gattc_write_flat(conn_handle, g_pmd_cccd_handle,
                                          notify_on, sizeof(notify_on),
                                          NULL, "PMD_NOTIFY");
            if (rc != 0) {
                ESP_LOGE(TAG, "Notify enable failed: %d", rc);
            }
        }
        return 0;
    }

    if (ble_uuid_u16(&dsc->uuid.u) == 0x2902) {
        g_pmd_cccd_handle = dsc->handle;
    }
    return 0;
}

static int chr_disc_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                       const struct ble_gatt_chr *chr, void *arg) {
    if (error->status == BLE_HS_EDONE) {
        if (g_pmd_data_handle) {
            int rc = ble_gattc_disc_all_dscs(conn_handle, g_pmd_data_handle,
                                             g_pmd_end, dsc_disc_cb, NULL);
            if (rc != 0) {
                ESP_LOGE(TAG, "Descriptor discovery failed: %d", rc);
            }
        }
        return 0;
    }

    if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_CTRL.u) == 0) {
        g_pmd_ctrl_handle = chr->val_handle;
    } else if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_DATA.u) == 0) {
        g_pmd_data_handle = chr->val_handle;
    }
    return 0;
}

static int svc_disc_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                       const struct ble_gatt_svc *svc, void *arg) {
    if (error->status == BLE_HS_EDONE) {
        if (g_pmd_start > 0) {
            int rc = ble_gattc_disc_all_chrs(conn_handle, g_pmd_start, g_pmd_end,
                                             chr_disc_cb, NULL);
            if (rc != 0) {
                ESP_LOGE(TAG, "Characteristic discovery failed: %d", rc);
            }
        } else {
            ESP_LOGE(TAG, "PMD Service not found!");
        }
        return 0;
    }

    if (ble_uuid_cmp(&svc->uuid.u, &UUID_PMD_SVC.u) == 0) {
        g_pmd_start = svc->start_handle;
        g_pmd_end = svc->end_handle;
    }
    return 0;
}

static int gap_event(struct ble_gap_event *event, void *arg) {
    switch (event->type) {

    case BLE_GAP_EVENT_DISC: {
        if (g_connecting || g_connected) return 0;

        const struct ble_gap_disc_desc *desc = &event->disc;
        char device_name[64] = {0};
        if (!parse_adv_name(desc->data, desc->length_data, device_name, sizeof(device_name))) {
            return 0;
        }

        if (strcmp(device_name, g_target_device_name) != 0) {
            return 0;
        }

        char addr_str[18];
        addr_to_str(&desc->addr, addr_str, sizeof(addr_str));
        ESP_LOGI(TAG, "H10 found: %s (MAC: %s)", device_name, addr_str);

        g_connecting = true;
        ble_gap_disc_cancel();

        struct ble_gap_conn_params cp = {
            .scan_itvl = 0x0010,
            .scan_window = 0x0010,
            .itvl_min = 0x0018,
            .itvl_max = 0x0028,
            .latency = 0,
            .supervision_timeout = 300,
            .min_ce_len = 0,
            .max_ce_len = 0
        };

        ble_gap_connect(g_own_addr_type, &desc->addr, 30000, &cp, gap_event, NULL);
        return 0;
    }

    case BLE_GAP_EVENT_CONNECT: {
        if (event->connect.status != 0) {
            ESP_LOGW(TAG, "Failed to connect: %d", event->connect.status);
            g_connecting = false;
            start_scan();
            return 0;
        }

        g_conn_handle = event->connect.conn_handle;
        g_connected = true;
        g_connecting = false;
        ESP_LOGI(TAG, "Connected");

        g_pmd_start = g_pmd_end = 0;
        g_pmd_ctrl_handle = 0;
        g_pmd_data_handle = 0;
        g_pmd_cccd_handle = 0;

        ble_gattc_disc_all_svcs(g_conn_handle, svc_disc_cb, NULL);
        return 0;
    }

    case BLE_GAP_EVENT_DISCONNECT: {
        ESP_LOGW(TAG, "Disconnected: reason=%d", event->disconnect.reason);
        g_conn_handle = BLE_HS_CONN_HANDLE_NONE;
        g_connected = false;
        g_connecting = false;
        start_scan();
        return 0;
    }

    case BLE_GAP_EVENT_NOTIFY_RX: {
        if (event->notify_rx.attr_handle == g_pmd_data_handle) {
            struct os_mbuf *om = event->notify_rx.om;
            uint8_t *buf = om->om_data;
            int len = OS_MBUF_PKTLEN(om);
            if (len > 0) {
                parse_pmd_response(buf, len);
            }
        }
        return 0;
    }

    case BLE_GAP_EVENT_MTU:
    case BLE_GAP_EVENT_CONN_UPDATE:
    case BLE_GAP_EVENT_DISC_COMPLETE:
    default:
        return 0;
    }
}

int start_scan(void) {
    if (!has_target_device()) {
        return 0;
    }
    struct ble_gap_disc_params p;
    memset(&p, 0, sizeof(p));
    p.passive = 0;
    p.itvl = 0x0010;
    p.window = 0x0010;
    p.filter_duplicates = 1;

    ESP_LOGI(TAG, "Scanning...");
    return ble_gap_disc(g_own_addr_type, BLE_HS_FOREVER, &p, gap_event, NULL);
}

static void on_sync(void) {
    int rc = ble_hs_id_infer_auto(0, &g_own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "ID infer failed: %d", rc);
        return;
    }

    ESP_LOGI(TAG, "BLE ready");
    start_scan();
}

static void host_task(void *param) {
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void watchdog_task(void *param) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));

        if (g_connected && g_ecg_started && !g_acc_started && g_ecg_packet_count >= 2) {
            ESP_LOGI(TAG, "ECG streaming confirmed, starting ACC...");
            pmd_start_acc(g_conn_handle, g_pmd_ctrl_handle);
            g_acc_started = true;
        }

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

        if (g_connected) {
            ESP_LOGI(TAG,
                     "Status: ECG %lu pkt/%lu smp (%.1f Hz) | ACC %lu pkt/%lu smp (%.1f Hz) | Buf: ECG %d ACC %d",
                     g_ecg_packet_count, g_total_ecg_samples, ecg_rate,
                     g_acc_packet_count, g_total_acc_samples, acc_rate,
                     g_ecg_count, g_acc_count);
        }
    }
}

void ble_init(void) {
    nimble_port_init();
    ble_svc_gap_init();
    ble_svc_gatt_init();

    ble_svc_gap_device_name_set("ESP32C6-H10");
    ble_hs_cfg.sync_cb = on_sync;

    nimble_port_freertos_init(host_task);
}

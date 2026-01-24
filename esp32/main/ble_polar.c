#include "ble_polar.h"

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_timer.h"

#include "os/os_mbuf.h"

#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "host/ble_gatt.h"
#include "host/ble_uuid.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include "config_store.h"
#include "ecg_streaming.pb.h"
#include "state.h"
#include "usb_output.h"
#include "usb_transport.h"

static const char *TAG = "H10_COMBINED";

// PMD Service UUIDs
static const ble_uuid128_t UUID_PMD_SVC  = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x80,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_CTRL = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x81,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_DATA = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x82,0x5C,0x00,0xFB);

// PMD Measurement Types
#define PMD_TYPE_ECG 0x00
#define PMD_TYPE_ACC 0x02

static void addr_to_str(const ble_addr_t *addr, char *out, size_t out_len) {
    snprintf(out, out_len, "%02x:%02x:%02x:%02x:%02x:%02x",
            addr->val[5], addr->val[4], addr->val[3],
            addr->val[2], addr->val[1], addr->val[0]);
}

static bool parse_adv_name(const uint8_t *adv_data, uint8_t adv_len,
                          char *name_out, size_t name_out_len) {
    if (!adv_data || !name_out || name_out_len == 0) {
        return false;
    }

    uint8_t pos = 0;
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

static void parse_pmd_response(uint8_t *data, int len) {
    g_notification_count++;
    uint64_t now_us = (uint64_t)esp_timer_get_time();
    static uint64_t last_notif_us = 0;
    static uint64_t notif_index = 0;

    if (len < 2) {
        return;
    }

    uint8_t frame_type = data[0];
    uint8_t pmd_type = data[1];
    uint32_t debug_pmd_type =
        (frame_type == 0xF0 || frame_type == 0x80) ? pmd_type : frame_type;
    uint32_t sample_count = 0;
    uint64_t timestamp_ns = 0;

    switch (frame_type) {
        case 0xF0: // Settings Response
            ESP_LOGI(TAG, "Settings response for type 0x%02X", pmd_type);

            vTaskDelay(pdMS_TO_TICKS(300));
            if (pmd_type == PMD_TYPE_ECG && !g_ecg_started) {
                ESP_LOGI(TAG, "Starting ECG...");
                pmd_start_ecg(g_conn_handle, g_pmd_ctrl_handle);
            } else if (pmd_type == PMD_TYPE_ACC && !g_acc_started) {
                ESP_LOGI(TAG, "Starting ACC...");
                pmd_start_acc(g_conn_handle, g_pmd_ctrl_handle);
            }
            break;

        case 0x02: // ACC Measurement data
            if (len < 10) break;

            uint64_t acc_timestamp = 0;
            memcpy(&acc_timestamp, data + 1, 8);
            timestamp_ns = acc_timestamp;

            int acc_data_start = 10;
            int acc_data_len = len - acc_data_start;
            int num_acc_samples = acc_data_len / 6;
            sample_count = (uint32_t)num_acc_samples;

            g_acc_packet_count++;
            g_total_acc_samples += num_acc_samples;

            if (g_first_sample_time == 0) {
                g_first_sample_time = xTaskGetTickCount();
            }

            if (g_acc_count + num_acc_samples > MAX_ACC_SAMPLES) {
                output_acc_binary();
            }

            for (int i = 0; i < num_acc_samples && g_acc_count < MAX_ACC_SAMPLES; i++) {
                int offset = acc_data_start + i * 6;

                int16_t x = (int16_t)((data[offset+1] << 8) | data[offset+0]);
                int16_t y = (int16_t)((data[offset+3] << 8) | data[offset+2]);
                int16_t z = (int16_t)((data[offset+5] << 8) | data[offset+4]);

                int64_t sample_offset_ns =
                    ((int64_t)i - (int64_t)num_acc_samples + 1) * 1000000000LL / g_acc_sample_rate_hz;
                int64_t sample_timestamp_ns = (int64_t)acc_timestamp + sample_offset_ns;

                g_acc_buffer[g_acc_count].timestamp_ns = (uint64_t)sample_timestamp_ns;
                g_acc_buffer[g_acc_count].x_mg = x;
                g_acc_buffer[g_acc_count].y_mg = y;
                g_acc_buffer[g_acc_count].z_mg = z;
                g_acc_count++;
            }

            if (g_acc_count >= g_acc_batch_size) {
                output_acc_binary();
            }
            break;

        case 0x00: // ECG Measurement data
            if (len < 10) break;

            uint64_t timestamp = 0;
            memcpy(&timestamp, data + 1, 8);
            timestamp_ns = timestamp;

            int data_start = 10;
            int data_len = len - data_start;
            int num_samples = data_len / 3;
            sample_count = (uint32_t)num_samples;

            g_ecg_packet_count++;
            g_total_ecg_samples += num_samples;

            if (g_first_sample_time == 0) {
                g_first_sample_time = xTaskGetTickCount();
            }

            if (g_ecg_count + num_samples > MAX_ECG_SAMPLES) {
                output_ecg_binary();
            }

            for (int i = 0; i < num_samples && g_ecg_count < MAX_ECG_SAMPLES; i++) {
                int offset = data_start + i * 3;

                int32_t sample = (int32_t)(data[offset] |
                                           (data[offset+1] << 8) |
                                           (data[offset+2] << 16));

                if (sample & 0x800000) {
                    sample |= 0xFF000000;
                }

                int64_t sample_offset_ns =
                    ((int64_t)i - (int64_t)num_samples + 1) * 1000000000LL / g_ecg_sample_rate_hz;
                int64_t sample_timestamp_ns = (int64_t)timestamp + sample_offset_ns;

                g_ecg_buffer[g_ecg_count].timestamp_ns = (uint64_t)sample_timestamp_ns;
                g_ecg_buffer[g_ecg_count].value_uv = sample;
                g_ecg_count++;
            }

            if (g_ecg_count >= g_ecg_batch_size) {
                output_ecg_binary();
            }
            break;

        case 0x80: // Error
            ESP_LOGE(TAG, "PMD Error! type=0x%02X", pmd_type);
            if (len > 2) ESP_LOGE(TAG, "Error code: 0x%02X", data[2]);
            break;

        default:
            break;
    }

#if BINARY_OUTPUT_MODE && CONFIG_DEBUG_PMD_PROTO_ENABLE
    notif_index++;
    if (notif_index % CONFIG_DEBUG_PMD_PROTO_EVERY_N == 0) {
        ecg_streaming_BleNotificationDebug dbg =
            (ecg_streaming_BleNotificationDebug)ecg_streaming_BleNotificationDebug_init_zero;
        ecg_streaming_CollectorMessage msg =
            (ecg_streaming_CollectorMessage)ecg_streaming_CollectorMessage_init_zero;

        strlcpy(dbg.device_id, g_device_id, sizeof(dbg.device_id));
        dbg.frame_type = frame_type;
        dbg.pmd_type = debug_pmd_type;
        dbg.notif_len = (uint32_t)len;
        dbg.sample_count = sample_count;
        dbg.pmd_timestamp_ns = timestamp_ns;
        dbg.interval_ms = last_notif_us == 0 ? 0 : (uint32_t)((now_us - last_notif_us) / 1000);
        dbg.notification_index = notif_index;

        msg.which_message = ecg_streaming_CollectorMessage_ble_debug_tag;
        msg.message.ble_debug = dbg;
        usb_send_collector_message(&msg);
    }
#endif

    last_notif_us = now_us;
}

static int write_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                    struct ble_gatt_attr *attr, void *arg) {
    const char *what = (const char *)arg;

    if (error->status != 0) {
        ESP_LOGE(TAG, "WRITE %s failed: %d", what ? what : "?", error->status);
        return 0;
    }

    if (what && strcmp(what, "CCCD_PMD") == 0) {
        ESP_LOGI(TAG, "PMD notifications enabled");

        vTaskDelay(pdMS_TO_TICKS(500));
        g_last_command_time = xTaskGetTickCount();

        ESP_LOGI(TAG, "Starting ECG...");
        pmd_start_ecg(conn_handle, g_pmd_ctrl_handle);
    }

    return 0;
}

static int dsc_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       uint16_t chr_val_handle,
                       const struct ble_gatt_dsc *dsc,
                       void *arg) {
    if (error->status == 0) {
        if (ble_uuid_u16(&dsc->uuid.u) == 0x2902) {
            g_pmd_cccd_handle = dsc->handle;
        }
        return 0;
    }

    if (error->status == BLE_HS_EDONE) {
        if (g_pmd_cccd_handle) {
            uint8_t val[2] = {0x03, 0x00};
            int rc = ble_gattc_write_flat(conn_handle, g_pmd_cccd_handle,
                                          val, sizeof(val), write_cb, "CCCD_PMD");
            if (rc != 0) {
                ESP_LOGE(TAG, "CCCD enable failed: %d", rc);
            }
        }
        return 0;
    }

    return 0;
}

static int chr_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       const struct ble_gatt_chr *chr, void *arg) {
    if (error->status == 0) {
        if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_CTRL.u) == 0) {
            g_pmd_ctrl_handle = chr->val_handle;
        } else if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_DATA.u) == 0) {
            g_pmd_data_handle = chr->val_handle;
        }
        return 0;
    }

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

    return 0;
}

static int svc_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       const struct ble_gatt_svc *svc, void *arg) {
    if (error->status == 0) {
        if (ble_uuid_cmp(&svc->uuid.u, &UUID_PMD_SVC.u) == 0) {
            g_pmd_start = svc->start_handle;
            g_pmd_end   = svc->end_handle;
        }
        return 0;
    }

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
        g_target_addr = desc->addr;

        struct ble_gap_conn_params cp;
        memset(&cp, 0, sizeof(cp));
        cp.scan_itvl = 0x0010;
        cp.scan_window = 0x0010;
        cp.itvl_min = 0x000C;
        cp.itvl_max = 0x0018;
        cp.latency = 0;
        cp.supervision_timeout = 0x0100;
        cp.min_ce_len = 0;
        cp.max_ce_len = 0;

        ESP_LOGI(TAG, "Connecting...");
        int rc = ble_gap_connect(g_own_addr_type, &g_target_addr,
                                 30000, &cp, gap_event, NULL);
        if (rc != 0) {
            ESP_LOGE(TAG, "Connection failed: %d", rc);
            g_connecting = false;
            start_scan();
        }
        return 0;
    }

    case BLE_GAP_EVENT_NOTIFY_RX: {
        uint16_t h = event->notify_rx.attr_handle;
        struct os_mbuf *om = event->notify_rx.om;

        if (h == g_pmd_data_handle) {
            uint8_t buf[512];
            int n = om->om_len < (int)sizeof(buf) ? om->om_len : (int)sizeof(buf);
            os_mbuf_copydata(om, 0, n, buf);

            parse_pmd_response(buf, n);
        }
        return 0;
    }

    case BLE_GAP_EVENT_MTU: {
        ESP_LOGI(TAG, "MTU: %d", event->mtu.value);
        return 0;
    }

    case BLE_GAP_EVENT_CONNECT: {
        if (event->connect.status == 0) {
            g_conn_handle = event->connect.conn_handle;
            g_connected = true;
            g_notification_count = 0;
            g_last_command_time = 0;

            ESP_LOGI(TAG, "Connected!");

            int rc = ble_gattc_exchange_mtu(g_conn_handle, NULL, NULL);
            if (rc != 0) {
                ESP_LOGW(TAG, "MTU exchange failed: %d", rc);
            }

            g_pmd_start = g_pmd_end = 0;
            g_pmd_ctrl_handle = 0;
            g_pmd_data_handle = 0;
            g_pmd_cccd_handle = 0;
            g_ecg_packet_count = 0;
            g_acc_packet_count = 0;
            g_total_ecg_samples = 0;
            g_total_acc_samples = 0;
            g_first_sample_time = 0;
            g_ecg_count = 0;
            g_acc_count = 0;
            g_ecg_started = false;
            g_acc_started = false;

            rc = ble_gattc_disc_all_svcs(g_conn_handle, svc_disc_cb, NULL);
            if (rc != 0) {
                ESP_LOGE(TAG, "Service discovery failed: %d", rc);
            }
        } else {
            ESP_LOGE(TAG, "Connection failed: %d", event->connect.status);
            g_conn_handle = BLE_HS_CONN_HANDLE_NONE;
            g_connected = false;
            start_scan();
        }
        g_connecting = false;
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

    case BLE_GAP_EVENT_DISC_COMPLETE:
        return 0;

    case BLE_GAP_EVENT_CONN_UPDATE:
        return 0;

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

void ble_init(void) {
    nimble_port_init();
    ble_svc_gap_init();
    ble_svc_gatt_init();

    ble_svc_gap_device_name_set("ESP32C6-H10");
    ble_hs_cfg.sync_cb = on_sync;

    nimble_port_freertos_init(host_task);
}

void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle) {
    uint16_t ecg_rate = (uint16_t)g_ecg_sample_rate_hz;

    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ECG};

    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_simple, sizeof(cmd_simple),
                                  write_cb, "START_ECG_SIMPLE");
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
                              write_cb, "START_ECG_FULL");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ECG_FULL failed: %d", rc);
        return;
    }

    g_ecg_started = true;
}

void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle) {
    uint16_t acc_rate = (uint16_t)g_acc_sample_rate_hz;

    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ACC};

    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_simple, sizeof(cmd_simple),
                                  write_cb, "START_ACC_SIMPLE");
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
                              write_cb, "START_ACC_FULL");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ACC_FULL failed: %d", rc);
        return;
    }

    g_acc_started = true;
}

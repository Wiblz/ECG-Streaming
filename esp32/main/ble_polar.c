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
#include "nimble/nimble_npl.h"
#include "nimble/nimble_opt.h"
#include "syscfg/syscfg.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "host/ble_gatt.h"
#include "host/ble_uuid.h"
#include "host/ble_store.h"
#include "store/config/ble_store_config.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include "config_store.h"
#include "common.pb.h"
#include "esp_collector.pb.h"
#include "state.h"
#include "usb_output.h"
#include "usb_transport.h"
#include "led_status.h"

static const char *TAG = "H10_COMBINED";

void ble_store_config_init(void);

// PMD Service UUIDs
static const ble_uuid128_t UUID_PMD_SVC  = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x80,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_CTRL = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x81,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_DATA = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x82,0x5C,0x00,0xFB);

// PMD Measurement Types (default values; actual ECG type may vary by FW)
#define PMD_TYPE_ECG 0x00
#define PMD_TYPE_ACC 0x02

static struct ble_npl_event g_start_ecg_ev[MAX_POLAR_LINKS];
static struct ble_npl_event g_start_acc_ev[MAX_POLAR_LINKS];
static bool g_start_ecg_pending[MAX_POLAR_LINKS] = {false};
static bool g_start_acc_pending[MAX_POLAR_LINKS] = {false};
static bool g_start_ecg_wait_encryption[MAX_POLAR_LINKS] = {false};
static bool g_link_encrypted[MAX_POLAR_LINKS] = {false};
static bool g_cccd_pending[MAX_POLAR_LINKS] = {false};
static int g_link_index[MAX_POLAR_LINKS] = {0, 1};
#define PMD_SETTINGS_MIN_COMPLETE 8  // Minimum valid ECG settings (sample rate + resolution)

static void schedule_start_ecg(polar_link_t *link);
static void schedule_start_acc(polar_link_t *link);
static void start_ecg_ev_cb(struct ble_npl_event *ev);
static void start_acc_ev_cb(struct ble_npl_event *ev);
void ble_schedule_start_acc(void);
static void pmd_get_settings(uint16_t conn_handle, uint16_t ctrl_handle, uint8_t pmd_type);
static void pmd_try_enable_cccds(uint16_t conn_handle);
static void pmd_try_start_streams(uint16_t conn_handle);

typedef struct {
    const char *what;
    uint16_t conn_handle;
} write_ctx_t;

static write_ctx_t g_write_ctx_ctrl[MAX_POLAR_LINKS];
static write_ctx_t g_write_ctx_data[MAX_POLAR_LINKS];
static write_ctx_t g_write_ctx_start_ecg[MAX_POLAR_LINKS];
static write_ctx_t g_write_ctx_start_acc[MAX_POLAR_LINKS];
static write_ctx_t g_write_ctx_get_settings[MAX_POLAR_LINKS];

static int link_index(const polar_link_t *link) {
    if (!link) {
        return -1;
    }
    return (int)(link - g_links);
}
static polar_link_t *find_link_by_conn_handle(uint16_t conn_handle) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].conn_handle == conn_handle) {
            return &g_links[i];
        }
    }
    return NULL;
}

static polar_link_t *find_link_for_target(const char *device_name) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].in_use
            && !g_links[i].connected
            && !g_links[i].connecting
            && strcmp(g_links[i].target_device_name, device_name) == 0) {
            return &g_links[i];
        }
    }
    return NULL;
}

static bool any_connecting(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].connecting) {
            return true;
        }
    }
    return false;
}

static bool any_connected(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].connected) {
            return true;
        }
    }
    return false;
}

static bool has_pending_targets(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].in_use && !g_links[i].connected && !g_links[i].connecting) {
            return true;
        }
    }
    return false;
}

static void reset_link_state(polar_link_t *link) {
    link->pmd_start = 0;
    link->pmd_end = 0;
    link->pmd_ctrl_handle = 0;
    link->pmd_data_handle = 0;
    link->pmd_cccd_handle = 0;
    link->pmd_ctrl_cccd_handle = 0;
    link->ctrl_cccd_enabled = false;
    link->data_cccd_enabled = false;
    link->waiting_ecg_settings = false;
    link->ecg_settings_len = 0;
    link->acc_settings_len = 0;
    link->ecg_rate_selected = 0;
    link->ecg_resolution_selected = 0;
    link->acc_rate_selected = 0;
    link->acc_resolution_selected = 0;
    link->acc_range_selected = 0;
    link->ecg_rate_warned = false;
    link->acc_rate_warned = false;
    link->ecg_packet_count = 0;
    link->acc_packet_count = 0;
    link->total_ecg_samples = 0;
    link->total_acc_samples = 0;
    link->first_sample_time = 0;
    link->ecg_count = 0;
    link->acc_count = 0;
    link->ecg_started = false;
    link->acc_started = false;
}

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

static void parse_pmd_response(polar_link_t *link, uint8_t *data, int len) {
    g_notification_count++;
    uint64_t now_us = (uint64_t)esp_timer_get_time();
    static uint64_t last_notif_us = 0;
    static uint64_t notif_index = 0;

    if (len < 2) {
        return;
    }

    uint8_t frame_type = data[0];

    uint8_t pmd_type = data[1];
    uint32_t debug_pmd_type = 0;
    uint32_t sample_count = 0;
    uint64_t timestamp_ns = 0;
#if CONFIG_DEBUG_PMD_PROTO_ENABLE
    debug_pmd_type = (frame_type == 0xF0 || frame_type == 0x80) ? pmd_type : frame_type;
#endif

    switch (frame_type) {
        case 0xF0: { // Control Point Response
            // Format: [F0] [OpCode] [MeasurementType] [Status] [MoreFlag] [Parameters...]
            if (len < 5) {
                ESP_LOGW(TAG, "Control point response too short: len=%d", len);
                return;
            }

            uint8_t opcode = data[1];
            uint8_t measurement_type = data[2];
            uint8_t status = data[3];
            uint8_t more_flag = data[4];
            (void)more_flag;

            if (opcode == 0x02 && status != 0x00) {
                ESP_LOGE(TAG, "PMD start failed: type=0x%02X err=0x%02X",
                         measurement_type, status);
                return;
            }

            // Only process GET_SETTINGS responses (opcode 0x01)
            if (opcode != 0x01) {
                return; // Handled above or not a settings response
            }

            // Parse TLV settings starting at byte 5
            // TLV format: [Type][Count][Value(s)...]
            // Type 0: Sample rate (uint16), Type 1: Resolution (uint16)
            // Type 2: Range (uint16), Type 4: Channels (uint8), Type 5: Factor (float32)

            if (len > 5) {
                uint8_t settings_len = (uint8_t)(len - 5);
                const uint8_t *tlv_data = data + 5;

                // Parse TLV to identify sensor type by its characteristics
                uint16_t sample_rate = 0;
                uint16_t resolution = 0;
                uint16_t range = 0;
                uint8_t channels = 0;
                bool tlv_valid = false;

                int offset = 0;
                while (offset + 2 <= settings_len) {
                    uint8_t tlv_type = tlv_data[offset];
                    uint8_t tlv_count = tlv_data[offset + 1];
                    offset += 2;

                    if (tlv_type == 0) {
                        // Sample rate (uint16 little-endian)
                        // Count indicates number of available sample rates
                        if (offset + 2 * tlv_count <= settings_len) {
                            // Use the first sample rate as default
                            sample_rate = tlv_data[offset] | (tlv_data[offset + 1] << 8);
                            // Prefer requested rate if present
                            for (int i = 0; i < tlv_count; i++) {
                                uint16_t candidate = tlv_data[offset + i * 2] |
                                                    (tlv_data[offset + i * 2 + 1] << 8);
                                if (measurement_type == PMD_TYPE_ECG
                                    && candidate == (uint16_t)link->ecg_sample_rate_hz) {
                                    sample_rate = candidate;
                                }
                                if (measurement_type == PMD_TYPE_ACC
                                    && candidate == (uint16_t)link->acc_sample_rate_hz) {
                                    sample_rate = candidate;
                                }
                            }
                            offset += 2 * tlv_count;
                            tlv_valid = true;
                        } else {
                            ESP_LOGW(TAG, "TLV Type 0 (rate): insufficient data, count=%d", tlv_count);
                            break;
                        }
                    } else if (tlv_type == 1) {
                        // Resolution (uint16 little-endian)
                        if (offset + 2 * tlv_count <= settings_len) {
                            resolution = tlv_data[offset] | (tlv_data[offset + 1] << 8);
                            offset += 2 * tlv_count;
                        } else {
                            ESP_LOGW(TAG, "TLV Type 1 (res): insufficient data, count=%d", tlv_count);
                            break;
                        }
                    } else if (tlv_type == 4) {
                        // Channels (uint8)
                        if (offset + tlv_count <= settings_len) {
                            channels = tlv_data[offset];
                            offset += tlv_count;
                        } else {
                            ESP_LOGW(TAG, "TLV Type 4 (ch): insufficient data, count=%d", tlv_count);
                            break;
                        }
                    } else if (tlv_type == 2) {
                        // Range (uint16) - skip all values
                        if (offset + 2 * tlv_count <= settings_len) {
                            range = tlv_data[offset] | (tlv_data[offset + 1] << 8);
                            offset += 2 * tlv_count;
                        } else {
                            ESP_LOGW(TAG, "TLV Type 2 (range): insufficient data, count=%d", tlv_count);
                            break;
                        }
                    } else if (tlv_type == 5) {
                        // Factor (float32) - skip all values
                        if (offset + 4 * tlv_count <= settings_len) {
                            offset += 4 * tlv_count;
                        } else {
                            ESP_LOGW(TAG, "TLV Type 5 (factor): insufficient data, count=%d", tlv_count);
                            break;
                        }
                    } else {
                        // Unknown TLV type
                        ESP_LOGW(TAG, "Unknown TLV type=%d, count=%d at offset=%d", tlv_type, tlv_count, offset - 2);
                        break;
                    }
                }
                (void)channels;

                // ECG is always on measurement type 0x00 per official PMD spec Table 2
                // Identify by: sample_rate=130Hz, resolution=14-bit, valid TLV structure
                if (measurement_type == PMD_TYPE_ECG && tlv_valid) {
                    if (sample_rate == 130 && resolution == 14) {
                        // ECG settings found
                        if (settings_len > link->ecg_settings_len) {
                            link->ecg_settings_len = settings_len;
                            g_ecg_pmd_type = measurement_type;
                            link->ecg_rate_selected = sample_rate;
                            link->ecg_resolution_selected = resolution;
                            if (!link->ecg_rate_warned
                                && link->ecg_rate_selected != (uint16_t)link->ecg_sample_rate_hz) {
                                ESP_LOGW(TAG, "ECG rate %d not supported, using %d",
                                         link->ecg_sample_rate_hz, link->ecg_rate_selected);
                                link->ecg_rate_warned = true;
                            }
                            // Schedule START if ready
                            if (link->waiting_ecg_settings && !link->ecg_started &&
                                link->ecg_settings_len >= PMD_SETTINGS_MIN_COMPLETE) {
                                link->waiting_ecg_settings = false;
                                schedule_start_ecg(link);
                            }
                        }
                    }
                }

                // ACC is always on measurement type 0x02
                if (measurement_type == PMD_TYPE_ACC) {
                    if (tlv_valid) {
                        if (settings_len > link->acc_settings_len) {
                            link->acc_settings_len = settings_len;
                            g_acc_pmd_type = measurement_type;
                            link->acc_rate_selected = sample_rate;
                            link->acc_resolution_selected = resolution;
                            link->acc_range_selected = range;
                            if (!link->acc_rate_warned
                                && link->acc_rate_selected != (uint16_t)link->acc_sample_rate_hz) {
                                ESP_LOGW(TAG, "ACC rate %d not supported, using %d",
                                         link->acc_sample_rate_hz, link->acc_rate_selected);
                                link->acc_rate_warned = true;
                            }
                        }
                    }
                }
            }
            break;
        }

        case 0x02: // ACC Measurement data
            led_status_mark_stream_activity(link_index(link));
            if (len < 10) break;

            uint64_t acc_timestamp_ns = 0;
            memcpy(&acc_timestamp_ns, data + 1, 8);
#if CONFIG_DEBUG_PMD_PROTO_ENABLE
            timestamp_ns = acc_timestamp_ns;
#endif

            int acc_data_start = 10;
            int acc_data_len = len - acc_data_start;

            link->acc_packet_count++;

            // ACC is 16-bit per axis (3 axes) = 6 bytes per sample
            int acc_num_samples = acc_data_len / 6;
            link->total_acc_samples += acc_num_samples;

            // Send raw frame data with PMD timestamp (convert ns to us) and ESP timestamp
            output_sensor_frame(
                link->target_device_name,
                ecg_streaming_SensorType_SENSOR_TYPE_ACCELEROMETER,
                link->acc_sample_rate_hz,
                acc_timestamp_ns / 1000,
                data + acc_data_start,
                acc_data_len
            );
            break;

        case 0x00: // ECG Measurement data
            led_status_mark_stream_activity(link_index(link));
            if (len < 10) break;

            uint64_t ecg_timestamp_ns = 0;
            memcpy(&ecg_timestamp_ns, data + 1, 8);
#if CONFIG_DEBUG_PMD_PROTO_ENABLE
            timestamp_ns = ecg_timestamp_ns;
#endif

            int data_start = 10;
            int data_len = len - data_start;

            link->ecg_packet_count++;

            // ECG is 14-bit = 24-bit per 3 samples, packed as 3 bytes per sample
            int num_samples = data_len / 3;
            link->total_ecg_samples += num_samples;

            if (link->first_sample_time == 0) link->first_sample_time = xTaskGetTickCount();

            // Send raw frame data with PMD timestamp (convert ns to us) and ESP timestamp
            output_sensor_frame(
                link->target_device_name,
                ecg_streaming_SensorType_SENSOR_TYPE_ECG,
                link->ecg_sample_rate_hz > 0 ? link->ecg_sample_rate_hz : 130,
                ecg_timestamp_ns / 1000,
                data + data_start,
                data_len
            );
            break;

        case 0x80: // Error
            ESP_LOGE(TAG, "PMD Error! type=0x%02X", pmd_type);
            if (len > 2) ESP_LOGE(TAG, "Error code: 0x%02X", data[2]);
            if (len > 0) {
                char hex[256] = {0};
                int pos = 0;
                for (int i = 0; i < len && pos < (int)sizeof(hex) - 4; i++) {
                    pos += snprintf(hex + pos, sizeof(hex) - pos, "%02X ", data[i]);
                }
                ESP_LOGE(TAG, "PMD error raw: %s", hex);
            }
            break;

        default:
            break;
    }

    last_notif_us = now_us;
#if CONFIG_DEBUG_PMD_PROTO_ENABLE
    notif_index++;
    if (notif_index % CONFIG_DEBUG_PMD_PROTO_EVERY_N == 0) {
        ecg_streaming_BleNotificationDebug dbg =
            (ecg_streaming_BleNotificationDebug)ecg_streaming_BleNotificationDebug_init_zero;
        ecg_streaming_EspMessage msg =
            (ecg_streaming_EspMessage)ecg_streaming_EspMessage_init_zero;

        strlcpy(dbg.device_id, link->target_device_name, sizeof(dbg.device_id));
        dbg.frame_type = frame_type;
        dbg.pmd_type = debug_pmd_type;
        dbg.notif_len = (uint32_t)len;
        dbg.sample_count = sample_count;
        dbg.polar_clock_us = timestamp_ns / 1000;  // Convert ns to us
        dbg.interval_us = last_notif_us == 0 ? 0 : (uint32_t)(now_us - last_notif_us);
        dbg.notification_index = notif_index;
        dbg.conn_interval_ms = g_conn_interval_ms;
        dbg.mtu = g_current_mtu;

        msg.which_message = ecg_streaming_EspMessage_ble_debug_tag;
        msg.message.ble_debug = dbg;
        usb_send_esp_message(&msg);
    }
#else
    (void)sample_count;
    (void)timestamp_ns;
    (void)debug_pmd_type;
    (void)notif_index;
#endif
}

static int write_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                    struct ble_gatt_attr *attr, void *arg) {
    write_ctx_t *ctx = (write_ctx_t *)arg;
    const char *what = ctx ? ctx->what : NULL;
    if (ctx) {
        conn_handle = ctx->conn_handle;
    }

    if (error->status != 0) {
        ESP_LOGE(TAG, "WRITE %s failed: %d", what ? what : "?", error->status);
        return 0;
    }

    // Only log important writes
    if (what && (strcmp(what, "CCCD_PMD") == 0 || strcmp(what, "START_ECG") == 0)) {
        ESP_LOGI(TAG, "WRITE %s ok", what);
    }

    if (what && strcmp(what, "CCCD_PMD_CTRL") == 0) {
        polar_link_t *link = find_link_by_conn_handle(conn_handle);
        if (link) {
            link->ctrl_cccd_enabled = true;
        }
        pmd_try_start_streams(conn_handle);
    }

    if (what && strcmp(what, "CCCD_PMD") == 0) {
        polar_link_t *link = find_link_by_conn_handle(conn_handle);
        if (link) {
            link->data_cccd_enabled = true;
        }
        pmd_try_start_streams(conn_handle);
    }

    return 0;
}

static void schedule_start_ecg(polar_link_t *link) {
    int idx = link_index(link);
    if (idx < 0) {
        return;
    }
    if (g_start_ecg_pending[idx]) {
        return;
    }
    g_start_ecg_pending[idx] = true;
    ble_npl_eventq_put(nimble_port_get_dflt_eventq(), &g_start_ecg_ev[idx]);
}

static void schedule_start_acc(polar_link_t *link) {
    int idx = link_index(link);
    if (idx < 0) {
        return;
    }
    if (g_start_acc_pending[idx]) {
        return;
    }
    g_start_acc_pending[idx] = true;
    ble_npl_eventq_put(nimble_port_get_dflt_eventq(), &g_start_acc_ev[idx]);
}

static void start_ecg_ev_cb(struct ble_npl_event *ev) {
    int idx = *(int *)ble_npl_event_get_arg(ev);
    struct ble_gap_conn_desc desc;
    g_start_ecg_pending[idx] = false;
    polar_link_t *link = &g_links[idx];

    if (link->conn_handle == BLE_HS_CONN_HANDLE_NONE || link->pmd_ctrl_handle == 0) {
        ESP_LOGW(TAG, "ECG start skipped: invalid handles");
        return;
    }
    if (ble_gap_conn_find(link->conn_handle, &desc) != 0) {
        ESP_LOGW(TAG, "ECG start aborted: not connected");
        return;
    }

    g_last_command_time = xTaskGetTickCount();
    if (link->ecg_sample_rate_hz > 0) {
        ESP_LOGI(TAG, "Starting ECG...");
        pmd_start_ecg(link->conn_handle, link->pmd_ctrl_handle);
    }
}

static void start_acc_ev_cb(struct ble_npl_event *ev) {
    int idx = *(int *)ble_npl_event_get_arg(ev);
    struct ble_gap_conn_desc desc;
    g_start_acc_pending[idx] = false;
    polar_link_t *link = &g_links[idx];

    if (link->conn_handle == BLE_HS_CONN_HANDLE_NONE || link->pmd_ctrl_handle == 0) {
        ESP_LOGW(TAG, "ACC start skipped: invalid handles");
        return;
    }
    if (ble_gap_conn_find(link->conn_handle, &desc) != 0) {
        ESP_LOGW(TAG, "ACC start aborted: not connected");
        return;
    }

    ESP_LOGI(TAG, "Starting ACC...");
    pmd_start_acc(link->conn_handle, link->pmd_ctrl_handle);
}

void ble_schedule_start_acc(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].connected) {
            schedule_start_acc(&g_links[i]);
        }
    }
}

static void pmd_try_enable_cccds(uint16_t conn_handle) {
    polar_link_t *link = find_link_by_conn_handle(conn_handle);
    if (!link) {
        return;
    }
    int idx = link_index(link);
    if (idx < 0) {
        return;
    }
    if (!g_link_encrypted[idx]) {
        g_cccd_pending[idx] = true;
        int rc = ble_gap_security_initiate(conn_handle);
        if (rc != 0 && rc != BLE_HS_EALREADY) {
            ESP_LOGW(TAG, "Security initiate failed: %d", rc);
        }
        return;
    }

    if (link->pmd_ctrl_cccd_handle && !link->ctrl_cccd_enabled) {
        uint8_t val[2] = {0x02, 0x00}; // indicate
        write_ctx_t *ctx = NULL;
        if (idx >= 0) {
            g_write_ctx_ctrl[idx].what = "CCCD_PMD_CTRL";
            g_write_ctx_ctrl[idx].conn_handle = conn_handle;
            ctx = &g_write_ctx_ctrl[idx];
        }
        int rc = ble_gattc_write_flat(conn_handle, link->pmd_ctrl_cccd_handle,
                                      val, sizeof(val), write_cb, ctx);
        if (rc != 0) {
            ESP_LOGE(TAG, "CCCD ctrl enable failed: %d", rc);
        }
    }

    if (link->pmd_cccd_handle && !link->data_cccd_enabled) {
        uint8_t val[2] = {0x01, 0x00}; // notify
        write_ctx_t *ctx = NULL;
        if (idx >= 0) {
            g_write_ctx_data[idx].what = "CCCD_PMD";
            g_write_ctx_data[idx].conn_handle = conn_handle;
            ctx = &g_write_ctx_data[idx];
        }
        int rc = ble_gattc_write_flat(conn_handle, link->pmd_cccd_handle,
                                      val, sizeof(val), write_cb, ctx);
        if (rc != 0) {
            ESP_LOGE(TAG, "CCCD data enable failed: %d", rc);
        }
    }
}

static void pmd_try_start_streams(uint16_t conn_handle) {
    polar_link_t *link = find_link_by_conn_handle(conn_handle);
    if (!link) {
        return;
    }
    int idx = link_index(link);
    if (idx < 0) {
        return;
    }
    if (!g_link_encrypted[idx]) {
        g_start_ecg_wait_encryption[idx] = true;
        int rc = ble_gap_security_initiate(conn_handle);
        if (rc != 0 && rc != BLE_HS_EALREADY) {
            ESP_LOGW(TAG, "Security initiate failed: %d", rc);
        }
        return;
    }

    if (link->ctrl_cccd_enabled && link->data_cccd_enabled) {
        link->waiting_ecg_settings = true;
        // Per official Polar PMD spec Table 2: ECG=0x00, PPG=0x01, ACC=0x02
        // Query only the official measurement types (no heuristic type detection)
        pmd_get_settings(conn_handle, link->pmd_ctrl_handle, PMD_TYPE_ECG);  // 0x00
        pmd_get_settings(conn_handle, link->pmd_ctrl_handle, PMD_TYPE_ACC);  // 0x02
    }
}

static int dsc_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       uint16_t chr_val_handle,
                       const struct ble_gatt_dsc *dsc,
                       void *arg) {
    polar_link_t *link = (polar_link_t *)arg;
    if (error->status == 0) {
        if (ble_uuid_u16(&dsc->uuid.u) == 0x2902) {
            if (link && dsc->handle == (uint16_t)(link->pmd_ctrl_handle + 1)) {
                link->pmd_ctrl_cccd_handle = dsc->handle;
                ESP_LOGI(TAG, "PMD CTRL CCCD handle: 0x%04X", link->pmd_ctrl_cccd_handle);
            } else if (link && dsc->handle == (uint16_t)(link->pmd_data_handle + 1)) {
                link->pmd_cccd_handle = dsc->handle;
                ESP_LOGI(TAG, "PMD DATA CCCD handle: 0x%04X", link->pmd_cccd_handle);
            } else {
                ESP_LOGW(TAG, "PMD CCCD at 0x%04X (chr=0x%04X) not matched",
                         dsc->handle, chr_val_handle);
            }
        }
        return 0;
    }

    if (error->status == BLE_HS_EDONE) {
        pmd_try_enable_cccds(conn_handle);
        return 0;
    }

    return 0;
}

static int chr_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       const struct ble_gatt_chr *chr, void *arg) {
    polar_link_t *link = (polar_link_t *)arg;
    if (error->status == 0) {
        if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_CTRL.u) == 0) {
            if (link) {
                link->pmd_ctrl_handle = chr->val_handle;
            }
        } else if (ble_uuid_cmp(&chr->uuid.u, &UUID_PMD_DATA.u) == 0) {
            if (link) {
                link->pmd_data_handle = chr->val_handle;
            }
        }
        return 0;
    }

    if (error->status == BLE_HS_EDONE) {
        if (link && link->pmd_ctrl_handle) {
            int rc = ble_gattc_disc_all_dscs(conn_handle, link->pmd_ctrl_handle,
                                            link->pmd_end, dsc_disc_cb, link);
            if (rc != 0) {
                ESP_LOGE(TAG, "Descriptor discovery (ctrl) failed: %d", rc);
            }
        }
        if (link && link->pmd_data_handle) {
            int rc = ble_gattc_disc_all_dscs(conn_handle, link->pmd_data_handle,
                                            link->pmd_end, dsc_disc_cb, link);
            if (rc != 0) {
                ESP_LOGE(TAG, "Descriptor discovery (data) failed: %d", rc);
            }
        }
        ESP_LOGI(TAG, "PMD handles: ctrl=0x%04X data=0x%04X ctrl_cccd=0x%04X data_cccd=0x%04X",
                 link ? link->pmd_ctrl_handle : 0,
                 link ? link->pmd_data_handle : 0,
                 link ? link->pmd_ctrl_cccd_handle : 0,
                 link ? link->pmd_cccd_handle : 0);
        return 0;
    }

    return 0;
}

static int svc_disc_cb(uint16_t conn_handle,
                       const struct ble_gatt_error *error,
                       const struct ble_gatt_svc *svc, void *arg) {
    polar_link_t *link = (polar_link_t *)arg;
    if (error->status == 0) {
        if (ble_uuid_cmp(&svc->uuid.u, &UUID_PMD_SVC.u) == 0) {
            if (link) {
                link->pmd_start = svc->start_handle;
                link->pmd_end   = svc->end_handle;
            }
        }
        return 0;
    }

    if (error->status == BLE_HS_EDONE) {
        if (link && link->pmd_start > 0) {
            int rc = ble_gattc_disc_all_chrs(conn_handle, link->pmd_start, link->pmd_end,
                                            chr_disc_cb, link);
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
        if (any_connecting()) return 0;

        const struct ble_gap_disc_desc *desc = &event->disc;

        char device_name[64] = {0};
        if (!parse_adv_name(desc->data, desc->length_data, device_name, sizeof(device_name))) {
            return 0;
        }

        polar_link_t *link = find_link_for_target(device_name);
        if (!link) {
            return 0;
        }

        char addr_str[18];
        addr_to_str(&desc->addr, addr_str, sizeof(addr_str));
        ESP_LOGI(TAG, "H10 found: %s (MAC: %s)", device_name, addr_str);

        link->connecting = true;
        ble_gap_disc_cancel();
        link->target_addr = desc->addr;

        struct ble_gap_conn_params cp;
        memset(&cp, 0, sizeof(cp));
        cp.scan_itvl = 0x0010;
        cp.scan_window = 0x0010;
        cp.itvl_min = 0x0006;
        cp.itvl_max = 0x000C;
        cp.latency = 0;
        cp.supervision_timeout = 0x0100;
        cp.min_ce_len = 0;
        cp.max_ce_len = 0;

        ESP_LOGI(TAG, "Connecting...");
        int rc = ble_gap_connect(g_own_addr_type, &link->target_addr,
                                 30000, &cp, gap_event, link);
        if (rc != 0) {
            ESP_LOGE(TAG, "Connection failed: %d", rc);
            link->connecting = false;
            start_scan();
        }
        return 0;
    }

    case BLE_GAP_EVENT_NOTIFY_RX: {
        polar_link_t *link = find_link_by_conn_handle(event->notify_rx.conn_handle);
        if (!link) {
            return 0;
        }
        uint16_t h = event->notify_rx.attr_handle;
        struct os_mbuf *om = event->notify_rx.om;
        int pkt_len = OS_MBUF_PKTLEN(om);

        if (h == link->pmd_data_handle || h == link->pmd_ctrl_handle) {
            uint8_t buf[512];
            int n = pkt_len < (int)sizeof(buf) ? pkt_len : (int)sizeof(buf);
            os_mbuf_copydata(om, 0, n, buf);

            parse_pmd_response(link, buf, n);
        } else {
            static uint32_t unknown_notif = 0;
            if (unknown_notif++ < 5) {
                ESP_LOGW(TAG, "Notify on UNKNOWN handle 0x%04X (ctrl=0x%04X, data=0x%04X) len=%d",
                         h, link->pmd_ctrl_handle, link->pmd_data_handle, pkt_len);
            }
        }
        return 0;
    }

    case BLE_GAP_EVENT_MTU: {
        g_current_mtu = event->mtu.value;
        return 0;
    }

    case BLE_GAP_EVENT_CONNECT: {
        polar_link_t *link = (polar_link_t *)arg;
        if (!link) {
            return 0;
        }
        int idx = link_index(link);
        if (event->connect.status == 0) {
            link->conn_handle = event->connect.conn_handle;
            link->connected = true;
            link->connecting = false;
            led_status_set_polar_connected(any_connected());
            g_link_encrypted[idx] = false;
            g_start_ecg_wait_encryption[idx] = false;
            g_cccd_pending[idx] = false;
            g_notification_count = 0;
            g_last_command_time = 0;

            ESP_LOGI(TAG, "Connected!");
            // Request large MTU for ECG data streaming
            // Per ESP32 GitHub issue #249: MTU=232 is critical for H10 PMD streaming
            int rc = ble_att_set_preferred_mtu(247);  // Request 247 (max for BLE 4.2)
            if (rc != 0) {
                ESP_LOGW(TAG, "Set preferred MTU failed: %d", rc);
            }

            rc = ble_gattc_exchange_mtu(link->conn_handle, NULL, NULL);
            if (rc != 0) {
                ESP_LOGW(TAG, "MTU exchange failed: %d", rc);
            }
            struct ble_gap_conn_desc desc;
            if (ble_gap_conn_find(link->conn_handle, &desc) == 0) {
                g_conn_interval_ms = (uint32_t)(desc.conn_itvl * 1.25f);
            }

            reset_link_state(link);
            g_ecg_pmd_type = PMD_TYPE_ECG;  // Reset to default, will be detected
            g_acc_pmd_type = PMD_TYPE_ACC;

            rc = ble_gattc_disc_all_svcs(link->conn_handle, svc_disc_cb, link);
            if (rc != 0) {
                ESP_LOGE(TAG, "Service discovery failed: %d", rc);
            }

            rc = ble_gap_security_initiate(link->conn_handle);
            if (rc != 0 && rc != BLE_HS_EALREADY) {
                ESP_LOGW(TAG, "Security initiation failed: %d (device may not require it)", rc);
            }

            if (has_pending_targets()) {
                start_scan();
            }
        } else {
            ESP_LOGE(TAG, "Connection failed: %d", event->connect.status);
            link->conn_handle = BLE_HS_CONN_HANDLE_NONE;
            link->connected = false;
            link->connecting = false;
            led_status_set_polar_connected(any_connected());
            if (has_pending_targets()) {
                start_scan();
            }
        }
        return 0;
    }

    case BLE_GAP_EVENT_DISCONNECT: {
        ESP_LOGW(TAG, "Disconnected: reason=%d", event->disconnect.reason);
        polar_link_t *link = find_link_by_conn_handle(event->disconnect.conn.conn_handle);
        if (link) {
            int idx = link_index(link);
            link->conn_handle = BLE_HS_CONN_HANDLE_NONE;
            link->connected = false;
            link->connecting = false;
            g_link_encrypted[idx] = false;
            g_start_ecg_wait_encryption[idx] = false;
            g_cccd_pending[idx] = false;
            reset_link_state(link);
        }
        g_ecg_pmd_type = PMD_TYPE_ECG;  // Reset to default
        g_acc_pmd_type = PMD_TYPE_ACC;
        led_status_set_polar_connected(any_connected());
        if (has_pending_targets()) {
            start_scan();
        }
        return 0;
    }

    case BLE_GAP_EVENT_DISC_COMPLETE:
        return 0;

    case BLE_GAP_EVENT_CONN_UPDATE:
        {
            struct ble_gap_conn_desc desc;
            if (ble_gap_conn_find(event->conn_update.conn_handle, &desc) == 0) {
                g_conn_interval_ms = (uint32_t)(desc.conn_itvl * 1.25f);
            }
        }
        return 0;

    case BLE_GAP_EVENT_ENC_CHANGE: {
        struct ble_gap_conn_desc desc;
        int rc = ble_gap_conn_find(event->enc_change.conn_handle, &desc);
        if (rc == 0) {
            polar_link_t *link = find_link_by_conn_handle(event->enc_change.conn_handle);
            int idx = link_index(link);
            ESP_LOGI(TAG, "Encryption change: status=%d encrypted=%d authenticated=%d bonded=%d",
                     event->enc_change.status,
                     desc.sec_state.encrypted,
                     desc.sec_state.authenticated,
                     desc.sec_state.bonded);
            if (idx >= 0) {
                g_link_encrypted[idx] = desc.sec_state.encrypted;
                if (g_link_encrypted[idx] && g_start_ecg_wait_encryption[idx]) {
                    g_start_ecg_wait_encryption[idx] = false;
                    schedule_start_ecg(link);
                }
                if (g_link_encrypted[idx] && g_cccd_pending[idx]) {
                    g_cccd_pending[idx] = false;
                    pmd_try_enable_cccds(event->enc_change.conn_handle);
                }
            }
        }
        return 0;
    }

    case BLE_GAP_EVENT_PASSKEY_ACTION: {
        ESP_LOGI(TAG, "Passkey action: action=%d", event->passkey.params.action);
        // For just-works pairing (no passkey needed)
        struct ble_sm_io pkey = {0};
        pkey.action = event->passkey.params.action;
        int rc = ble_sm_inject_io(event->passkey.conn_handle, &pkey);
        if (rc != 0) {
            ESP_LOGE(TAG, "Passkey inject failed: %d", rc);
        }
        return 0;
    }

    default:
        return 0;
    }
}

int start_scan(void) {
    if (!has_pending_targets()) {
        return 0;
    }
    if (any_connecting()) {
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

    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        ble_npl_event_init(&g_start_ecg_ev[i], start_ecg_ev_cb, &g_link_index[i]);
        ble_npl_event_init(&g_start_acc_ev[i], start_acc_ev_cb, &g_link_index[i]);
    }

    ble_svc_gap_device_name_set("ESP32C6-H10");

    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 0;
    ble_hs_cfg.sm_sc = 1;
    ble_hs_cfg.sm_io_cap = BLE_HS_IO_NO_INPUT_OUTPUT;
    ble_hs_cfg.sm_our_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    ble_hs_cfg.sync_cb = on_sync;

    ble_store_config_init();
    nimble_port_freertos_init(host_task);
}

static void pmd_get_settings(uint16_t conn_handle, uint16_t ctrl_handle, uint8_t pmd_type) {
    uint8_t cmd[2] = {0x01, pmd_type};
    polar_link_t *link = find_link_by_conn_handle(conn_handle);
    int idx = link_index(link);
    write_ctx_t *ctx = NULL;
    if (idx >= 0) {
        g_write_ctx_get_settings[idx].what = "GET_SETTINGS";
        g_write_ctx_get_settings[idx].conn_handle = conn_handle;
        ctx = &g_write_ctx_get_settings[idx];
    }
    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd, sizeof(cmd),
                                  write_cb, ctx);
    if (rc != 0) {
        ESP_LOGE(TAG, "GET_SETTINGS failed: %d", rc);
    }
}

void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle) {
    polar_link_t *link = find_link_by_conn_handle(conn_handle);
    int idx = link_index(link);
    if (!link) {
        return;
    }
    if (link->ecg_settings_len == 0) {
        ESP_LOGE(TAG, "No ECG settings available!");
        return;
    }

    // Build START command with selected settings
    // ECG: choose device-supported rate/resolution
    uint16_t desired_rate = link->ecg_rate_selected ? link->ecg_rate_selected
        : (uint16_t)link->ecg_sample_rate_hz;
    uint16_t desired_resolution = link->ecg_resolution_selected
        ? link->ecg_resolution_selected : 14;  // 14-bit fallback

    // Build TLV: [Type 0, Count 1, rate_lo, rate_hi]
    //            [Type 1, Count 1, res_lo, res_hi]
    uint8_t selected_settings[] = {
        0x00, 0x01, (uint8_t)(desired_rate & 0xFF), (uint8_t)((desired_rate >> 8) & 0xFF),
        0x01, 0x01, (uint8_t)(desired_resolution & 0xFF), (uint8_t)((desired_resolution >> 8) & 0xFF),
    };

    uint8_t cmd_full[2 + sizeof(selected_settings)];
    cmd_full[0] = 0x02;           // START command opcode
    cmd_full[1] = g_ecg_pmd_type; // Measurement type (0x00 for ECG)
    memcpy(cmd_full + 2, selected_settings, sizeof(selected_settings));

    ESP_LOGI(TAG, "Starting ECG stream: type=0x%02X, rate=%dHz, res=%dbit",
             g_ecg_pmd_type, desired_rate, desired_resolution);

    write_ctx_t *ctx = NULL;
    if (idx >= 0) {
        g_write_ctx_start_ecg[idx].what = "START_ECG";
        g_write_ctx_start_ecg[idx].conn_handle = conn_handle;
        ctx = &g_write_ctx_start_ecg[idx];
    }
    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_full, sizeof(cmd_full),
                                  write_cb, ctx);
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ECG write failed: %d", rc);
        return;
    }

    link->ecg_started = true;
}

void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle) {
    polar_link_t *link = find_link_by_conn_handle(conn_handle);
    int idx = link_index(link);
    if (!link) {
        return;
    }
    if (link->acc_settings_len == 0) {
        ESP_LOGE(TAG, "No ACC settings available!");
        return;
    }

    // Build START command with selected settings (not all available options)
    // GET_SETTINGS returns all available options, but START needs specific values
    // Format: [0x02] [MeasurementType] [TLV with selected settings]

    uint16_t desired_rate = link->acc_rate_selected ? link->acc_rate_selected
        : (uint16_t)link->acc_sample_rate_hz;
    uint16_t desired_resolution = link->acc_resolution_selected
        ? link->acc_resolution_selected : 16;  // 16-bit fallback
    uint16_t desired_range = link->acc_range_selected
        ? link->acc_range_selected : 8;        // ±8G fallback

    // Build TLV: [Type 0, Count 1, rate_lo, rate_hi]
    //            [Type 1, Count 1, res_lo, res_hi]
    //            [Type 2, Count 1, range_lo, range_hi]
    uint8_t selected_settings[] = {
        0x00, 0x01, (uint8_t)(desired_rate & 0xFF), (uint8_t)((desired_rate >> 8) & 0xFF),
        0x01, 0x01, (uint8_t)(desired_resolution & 0xFF), (uint8_t)((desired_resolution >> 8) & 0xFF),
        0x02, 0x01, (uint8_t)(desired_range & 0xFF), (uint8_t)((desired_range >> 8) & 0xFF),
    };

    uint8_t cmd_full[2 + sizeof(selected_settings)];
    cmd_full[0] = 0x02;           // START command opcode
    cmd_full[1] = g_acc_pmd_type; // Measurement type (0x02 for ACC)
    memcpy(cmd_full + 2, selected_settings, sizeof(selected_settings));

    ESP_LOGI(TAG, "Starting ACC stream: type=0x%02X, rate=%dHz, res=%dbit, range=±%dG",
             g_acc_pmd_type, desired_rate, desired_resolution, desired_range);

    write_ctx_t *ctx = NULL;
    if (idx >= 0) {
        g_write_ctx_start_acc[idx].what = "START_ACC";
        g_write_ctx_start_acc[idx].conn_handle = conn_handle;
        ctx = &g_write_ctx_start_acc[idx];
    }
    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle,
                                  cmd_full, sizeof(cmd_full),
                                  write_cb, ctx);
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ACC write failed: %d", rc);
        return;
    }

    link->acc_started = true;
}

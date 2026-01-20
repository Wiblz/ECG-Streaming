#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "nvs_flash.h"
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

#include "pb.h"
#include "pb_encode.h"
#include "ecg_streaming.pb.h"

static const char *TAG = "H10_COMBINED";
static const char *TARGET_DEVICE_NAME = CONFIG_POLAR_H10_NAME;
#define BINARY_OUTPUT_MODE CONFIG_BINARY_OUTPUT_MODE

#define DEVICE_ID CONFIG_DEVICE_ID

static uint8_t g_own_addr_type;
static ble_addr_t g_target_addr;
static uint16_t g_conn_handle = BLE_HS_CONN_HANDLE_NONE;

static bool g_connecting = false;
static bool g_connected  = false;

// PMD Service Handles
static uint16_t g_pmd_start = 0, g_pmd_end = 0;
static uint16_t g_pmd_ctrl_handle = 0;
static uint16_t g_pmd_data_handle = 0;
static uint16_t g_pmd_cccd_handle = 0;

static uint32_t g_notification_count = 0;
static TickType_t g_last_command_time = 0;
static uint32_t g_usb_seq = 0;

// PMD Measurement Types
#define PMD_TYPE_ECG 0x00
#define PMD_TYPE_ACC 0x02
#define ECG_SAMPLE_RATE_HZ CONFIG_ECG_SAMPLE_RATE
#define ACC_SAMPLE_RATE_HZ CONFIG_ACC_SAMPLE_RATE

// ECG Sample Structure
typedef struct {
    uint64_t timestamp_ns;
    int32_t value_uv;
} ecg_sample_t;

// ACC Sample Structure
typedef struct {
    uint64_t timestamp_ns;
    int16_t x_mg;
    int16_t y_mg;
    int16_t z_mg;
} acc_sample_t;

// Buffers
#define MAX_ECG_SAMPLES CONFIG_ECG_BATCH_SIZE
#define MAX_ACC_SAMPLES CONFIG_ACC_BATCH_SIZE
static ecg_sample_t g_ecg_buffer[MAX_ECG_SAMPLES];
static acc_sample_t g_acc_buffer[MAX_ACC_SAMPLES];
static int g_ecg_count = 0;
static int g_acc_count = 0;

// Statistics
static uint32_t g_ecg_packet_count = 0;
static uint32_t g_acc_packet_count = 0;
static uint32_t g_total_ecg_samples = 0;
static uint32_t g_total_acc_samples = 0;
static TickType_t g_first_sample_time = 0;

// State tracking
static bool g_ecg_started = false;
static bool g_acc_started = false;

// PMD Service UUIDs
static const ble_uuid128_t UUID_PMD_SVC  = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x80,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_CTRL = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x81,0x5C,0x00,0xFB);
static const ble_uuid128_t UUID_PMD_DATA = BLE_UUID128_INIT(
    0xC8,0xF0,0x8D,0x2D,0xCD,0x8A,0xAD,0x1C,0x87,0xF3,0xE7,0x02,0x82,0x5C,0x00,0xFB);

// Forward Declarations
static int start_scan(void);
static void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle);
static void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle);

// ============================================================================
// Helper Functions
// ============================================================================

static void addr_to_str(const ble_addr_t *addr, char *out, size_t out_len) {
    snprintf(out, out_len, "%02x:%02x:%02x:%02x:%02x:%02x",
            addr->val[5], addr->val[4], addr->val[3],
            addr->val[2], addr->val[1], addr->val[0]);
}

/**
 * Parse BLE advertising data to extract the device name.
 * Advertising data is in TLV format: [Length][Type][Value]...
 * AD Type 0x09 = Complete Local Name
 * AD Type 0x08 = Shortened Local Name
 *
 * Returns true if device name was found and extracted.
 */
static bool parse_adv_name(const uint8_t *adv_data, uint8_t adv_len,
                          char *name_out, size_t name_out_len) {
    if (!adv_data || !name_out || name_out_len == 0) {
        return false;
    }

    uint8_t pos = 0;
    while (pos < adv_len) {
        uint8_t length = adv_data[pos];

        // End of data or invalid length
        if (length == 0 || pos + length >= adv_len) {
            break;
        }

        uint8_t type = adv_data[pos + 1];

        // AD Type 0x09 = Complete Local Name
        // AD Type 0x08 = Shortened Local Name
        if (type == 0x09 || type == 0x08) {
            uint8_t name_len = length - 1; // Subtract type byte

            // Copy name (ensure null termination)
            size_t copy_len = name_len < (name_out_len - 1) ? name_len : (name_out_len - 1);
            memcpy(name_out, &adv_data[pos + 2], copy_len);
            name_out[copy_len] = '\0';

            return true;
        }

        pos += length + 1;
    }

    return false;
}

static uint32_t crc32_ieee(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

// ============================================================================
// Output Functions
// ============================================================================

#if BINARY_OUTPUT_MODE

// Static buffers for protobuf encoding (avoids stack overflow)
static uint8_t g_frame_buf[4096];
static uint8_t g_payload_buf[4096];
static ecg_streaming_ECGSampleBatch g_ecg_batch;
static ecg_streaming_AccelerometerSampleBatch g_acc_batch;
static ecg_streaming_CollectorMessage g_collector_msg;
static ecg_streaming_UsbFrame g_usb_frame;

typedef struct {
    const uint8_t *data;
    size_t len;
} bytes_view_t;

static bool encode_bytes_cb(pb_ostream_t *stream, const pb_field_t *field, void *const *arg) {
    const bytes_view_t *view = (const bytes_view_t *)(*arg);
    if (!pb_encode_tag_for_field(stream, field)) {
        return false;
    }
    return pb_encode_string(stream, view->data, view->len);
}

static bool send_usb_frame(ecg_streaming_UsbPayloadType type,
                           const uint8_t *payload, size_t payload_len) {
    bytes_view_t view = {
        .data = payload,
        .len = payload_len,
    };

    // Use static frame struct
    g_usb_frame = (ecg_streaming_UsbFrame)ecg_streaming_UsbFrame_init_zero;
    g_usb_frame.version = 1;
    g_usb_frame.payload_type = type;
    g_usb_frame.seq = g_usb_seq++;
    g_usb_frame.crc32 = crc32_ieee(payload, payload_len);
    g_usb_frame.payload.funcs.encode = encode_bytes_cb;
    g_usb_frame.payload.arg = (void *)&view;

    pb_ostream_t stream = pb_ostream_from_buffer(g_frame_buf, sizeof(g_frame_buf));
    if (!pb_encode(&stream, ecg_streaming_UsbFrame_fields, &g_usb_frame)) {
        ESP_LOGE(TAG, "UsbFrame encode failed");
        return false;
    }

    uint32_t frame_len = (uint32_t)stream.bytes_written;
    uint8_t len_le[4] = {
        (uint8_t)(frame_len & 0xFF),
        (uint8_t)((frame_len >> 8) & 0xFF),
        (uint8_t)((frame_len >> 16) & 0xFF),
        (uint8_t)((frame_len >> 24) & 0xFF),
    };

    fwrite(len_le, 1, sizeof(len_le), stdout);
    fwrite(g_frame_buf, 1, frame_len, stdout);
    fflush(stdout);
    return true;
}

static bool send_collector_message(const ecg_streaming_CollectorMessage *msg) {
    pb_ostream_t stream = pb_ostream_from_buffer(g_payload_buf, sizeof(g_payload_buf));

    if (!pb_encode(&stream, ecg_streaming_CollectorMessage_fields, msg)) {
        ESP_LOGE(TAG, "CollectorMessage encode failed");
        return false;
    }

    return send_usb_frame(ecg_streaming_UsbPayloadType_USB_PAYLOAD_TYPE_COLLECTOR_MESSAGE,
                          g_payload_buf, stream.bytes_written);
}

#endif // BINARY_OUTPUT_MODE

static void output_ecg_binary(void) {
    if (g_ecg_count == 0) return;

#if BINARY_OUTPUT_MODE
    // Use static structs to avoid stack overflow
    g_ecg_batch = (ecg_streaming_ECGSampleBatch)ecg_streaming_ECGSampleBatch_init_zero;
    g_collector_msg = (ecg_streaming_CollectorMessage)ecg_streaming_CollectorMessage_init_zero;

    strlcpy(g_ecg_batch.device_id, DEVICE_ID, sizeof(g_ecg_batch.device_id));
    g_ecg_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    g_ecg_batch.samples_count = (pb_size_t)g_ecg_count;

    for (int i = 0; i < g_ecg_count; i++) {
        ecg_streaming_ECGSample *sample = &g_ecg_batch.samples[i];
        sample->device_timestamp_us = (double)(g_ecg_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->raw_value = g_ecg_buffer[i].value_uv;
        sample->sample_rate = ECG_SAMPLE_RATE_HZ;
    }

    g_collector_msg.which_message = ecg_streaming_CollectorMessage_ecg_batch_tag;
    g_collector_msg.message.ecg_batch = g_ecg_batch;

    if (!send_collector_message(&g_collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ECG batch");
    }
#endif
    // In debug mode: no output here, just status in watchdog_task

    g_ecg_count = 0;
}

static void output_acc_binary(void) {
    if (g_acc_count == 0) return;

#if BINARY_OUTPUT_MODE
    // Use static structs to avoid stack overflow
    g_acc_batch = (ecg_streaming_AccelerometerSampleBatch)ecg_streaming_AccelerometerSampleBatch_init_zero;
    g_collector_msg = (ecg_streaming_CollectorMessage)ecg_streaming_CollectorMessage_init_zero;

    strlcpy(g_acc_batch.device_id, DEVICE_ID, sizeof(g_acc_batch.device_id));
    g_acc_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    g_acc_batch.samples_count = (pb_size_t)g_acc_count;

    for (int i = 0; i < g_acc_count; i++) {
        ecg_streaming_AccelerometerSample *sample = &g_acc_batch.samples[i];
        sample->device_timestamp_us = (double)(g_acc_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->x = (float)g_acc_buffer[i].x_mg / 1000.0f;
        sample->y = (float)g_acc_buffer[i].y_mg / 1000.0f;
        sample->z = (float)g_acc_buffer[i].z_mg / 1000.0f;
        sample->sample_rate = ACC_SAMPLE_RATE_HZ;
    }

    g_collector_msg.which_message = ecg_streaming_CollectorMessage_acc_batch_tag;
    g_collector_msg.message.acc_batch = g_acc_batch;

    if (!send_collector_message(&g_collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ACC batch");
    }
#endif
    // In debug mode: no output here, just status in watchdog_task

    g_acc_count = 0;
}

// ============================================================================
// PMD Data Parsing
// ============================================================================

static void parse_pmd_response(uint8_t *data, int len) {
    g_notification_count++;
    
    if (len < 2) {
        return;
    }

    uint8_t response_code = data[0];
    uint8_t measurement_type = data[1];

    switch (response_code) {
        case 0xF0: // Settings Response
            ESP_LOGI(TAG, "Settings response for type 0x%02X", measurement_type);
            
            vTaskDelay(pdMS_TO_TICKS(300));
            if (measurement_type == PMD_TYPE_ECG && !g_ecg_started) {
                ESP_LOGI(TAG, "Starting ECG...");
                pmd_start_ecg(g_conn_handle, g_pmd_ctrl_handle);
            } else if (measurement_type == PMD_TYPE_ACC && !g_acc_started) {
                ESP_LOGI(TAG, "Starting ACC...");
                pmd_start_acc(g_conn_handle, g_pmd_ctrl_handle);
            }
            break;
            
        case 0x02: // ACC Measurement data
            if (len < 10) break;
            
            // Parse timestamp (8 bytes little-endian, nanoseconds)
            uint64_t acc_timestamp = 0;
            memcpy(&acc_timestamp, data + 1, 8);
            
            int acc_data_start = 10;
            int acc_data_len = len - acc_data_start;
            int num_acc_samples = acc_data_len / 6;
            
            g_acc_packet_count++;
            g_total_acc_samples += num_acc_samples;
            
            if (g_first_sample_time == 0) {
                g_first_sample_time = xTaskGetTickCount();
            }
            
            // Reset buffer if full
            if (g_acc_count + num_acc_samples > MAX_ACC_SAMPLES) {
                output_acc_binary();
            }
            
            // Parse samples
            for (int i = 0; i < num_acc_samples && g_acc_count < MAX_ACC_SAMPLES; i++) {
                int offset = acc_data_start + i * 6;
                
                int16_t x = (int16_t)((data[offset+1] << 8) | data[offset+0]);
                int16_t y = (int16_t)((data[offset+3] << 8) | data[offset+2]);
                int16_t z = (int16_t)((data[offset+5] << 8) | data[offset+4]);
                
                int64_t sample_offset_ns =
                    ((int64_t)i - (int64_t)num_acc_samples + 1) * 1000000000LL / ACC_SAMPLE_RATE_HZ;
                int64_t sample_timestamp_ns = (int64_t)acc_timestamp + sample_offset_ns;

                g_acc_buffer[g_acc_count].timestamp_ns = (uint64_t)sample_timestamp_ns;
                g_acc_buffer[g_acc_count].x_mg = x;
                g_acc_buffer[g_acc_count].y_mg = y;
                g_acc_buffer[g_acc_count].z_mg = z;
                g_acc_count++;
            }
            
            // Output if buffer is getting full
            if (g_acc_count >= 50) {
                output_acc_binary();
            }
            break;
            
        case 0x00: // ECG Measurement data
            if (len < 10) break;
            
            // Parse timestamp (8 bytes little-endian, nanoseconds)
            uint64_t timestamp = 0;
            memcpy(&timestamp, data + 1, 8);
            
            int data_start = 10;
            int data_len = len - data_start;
            int num_samples = data_len / 3;
            
            g_ecg_packet_count++;
            g_total_ecg_samples += num_samples;
            
            if (g_first_sample_time == 0) {
                g_first_sample_time = xTaskGetTickCount();
            }
            
            // Reset buffer if full
            if (g_ecg_count + num_samples > MAX_ECG_SAMPLES) {
                output_ecg_binary();
            }
            
            // Parse samples
            for (int i = 0; i < num_samples && g_ecg_count < MAX_ECG_SAMPLES; i++) {
                int offset = data_start + i * 3;
                
                // 24-bit little-endian signed
                int32_t sample = (int32_t)(data[offset] | 
                                           (data[offset+1] << 8) | 
                                           (data[offset+2] << 16));
                
                // Sign extend from 24-bit to 32-bit
                if (sample & 0x800000) {
                    sample |= 0xFF000000;
                }
                
                int64_t sample_offset_ns =
                    ((int64_t)i - (int64_t)num_samples + 1) * 1000000000LL / ECG_SAMPLE_RATE_HZ;
                int64_t sample_timestamp_ns = (int64_t)timestamp + sample_offset_ns;

                g_ecg_buffer[g_ecg_count].timestamp_ns = (uint64_t)sample_timestamp_ns;
                g_ecg_buffer[g_ecg_count].value_uv = sample;
                g_ecg_count++;
            }
            
            // Output if buffer is getting full
            if (g_ecg_count >= 50) {
                output_ecg_binary();
            }
            break;
            
        case 0x80: // Error
            ESP_LOGE(TAG, "PMD Error! type=0x%02X", measurement_type);
            if (len > 2) ESP_LOGE(TAG, "Error code: 0x%02X", data[2]);
            break;
            
        default:
            break;
    }
}

// ============================================================================
// GATT Callbacks
// ============================================================================

static int write_cb(uint16_t conn_handle, const struct ble_gatt_error *error,
                    struct ble_gatt_attr *attr, void *arg)
{
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
                       void *arg)
{
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
                       const struct ble_gatt_chr *chr, void *arg)
{
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
                       const struct ble_gatt_svc *svc, void *arg)
{
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

// ============================================================================
// PMD Commands
// ============================================================================

static void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle)
{
    // Simple START command
    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ECG};
    
    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle, 
                                  cmd_simple, sizeof(cmd_simple),
                                  write_cb, "START_ECG_SIMPLE");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ECG_SIMPLE failed: %d", rc);
        return;
    }
    
    vTaskDelay(pdMS_TO_TICKS(1000));
    
    // Full settings: 130 Hz, 14-bit
    uint8_t cmd_full[10] = {
        0x02, 0x00,              // START, ECG
        0x00, 0x01, 0x82, 0x00,  // Sample Rate: 130 Hz
        0x01, 0x01, 0x0E, 0x00   // Resolution: 14-bit
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

static void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle)
{
    // Simple START command
    uint8_t cmd_simple[2] = {0x02, PMD_TYPE_ACC};
    
    int rc = ble_gattc_write_flat(conn_handle, ctrl_handle, 
                                  cmd_simple, sizeof(cmd_simple),
                                  write_cb, "START_ACC_SIMPLE");
    if (rc != 0) {
        ESP_LOGE(TAG, "START_ACC_SIMPLE failed: %d", rc);
        return;
    }
    
    vTaskDelay(pdMS_TO_TICKS(1000));
    
    // Full settings: 200 Hz, 16-bit, 2g range
    uint8_t cmd_full[14] = {
        0x02, 0x02,              // START, ACC
        0x00, 0x01, 0x64, 0x00,  // SAMPLE_RATE: 100 Hz (0x64 = 100)
        // 0x00, 0x01, 0xC8, 0x00,  // SAMPLE_RATE: 200 Hz (0xC8 = 200)
        0x01, 0x01, 0x10, 0x00,  // RESOLUTION: 16-bit
        0x02, 0x01, 0x02, 0x00   // RANGE: 2g
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

// ============================================================================
// GAP Event Handler
// ============================================================================

static int gap_event(struct ble_gap_event *event, void *arg) {
    switch (event->type) {

    case BLE_GAP_EVENT_DISC: {
        if (g_connecting || g_connected) return 0;

        const struct ble_gap_disc_desc *desc = &event->disc;

        // Extract device name from advertising data
        char device_name[64] = {0};
        if (!parse_adv_name(desc->data, desc->length_data, device_name, sizeof(device_name))) {
            // No device name in advertising data, skip this device
            return 0;
        }

        // Compare with target device name
        if (strcmp(device_name, TARGET_DEVICE_NAME) != 0) {
            return 0;
        }

        // Found the target device
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
            
            // Request larger MTU
            int rc = ble_gattc_exchange_mtu(g_conn_handle, NULL, NULL);
            if (rc != 0) {
                ESP_LOGW(TAG, "MTU exchange failed: %d", rc);
            }

            // Reset state
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

// ============================================================================
// Watchdog Task - Status every second
// ============================================================================

static void watchdog_task(void *param) {
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        
        // Start ACC after first ECG data arrives
        if (g_connected && g_ecg_started && !g_acc_started && g_ecg_packet_count >= 2) {
            ESP_LOGI(TAG, "ECG streaming confirmed, starting ACC...");
            pmd_start_acc(g_conn_handle, g_pmd_ctrl_handle);
            g_acc_started = true;
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

static int start_scan(void) {
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

// ============================================================================
// Main
// ============================================================================

void app_main(void) {
#if BINARY_OUTPUT_MODE
    // In binary mode, disable all logging to avoid corrupting USB framing
    esp_log_level_set("*", ESP_LOG_NONE);
#else
    // In human-readable mode, enable normal logging
    esp_log_level_set("*", ESP_LOG_INFO);
    esp_log_level_set("NimBLE", ESP_LOG_WARN);

    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "Polar H10 ECG + ACC Streamer");
    ESP_LOGI(TAG, "Device ID: %s", DEVICE_ID);
    ESP_LOGI(TAG, "Target Device: %s", TARGET_DEVICE_NAME);
    ESP_LOGI(TAG, "ECG: %d Hz | ACC: %d Hz", ECG_SAMPLE_RATE_HZ, ACC_SAMPLE_RATE_HZ);
    ESP_LOGI(TAG, "Mode: HUMAN READABLE");
    ESP_LOGI(TAG, "");
#endif

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    nimble_port_init();
    ble_svc_gap_init();
    ble_svc_gatt_init();

    ble_svc_gap_device_name_set("ESP32C6-H10");
    ble_hs_cfg.sync_cb = on_sync;

    nimble_port_freertos_init(host_task);
    
    xTaskCreate(watchdog_task, "watchdog", 4096, NULL, 5, NULL);
}

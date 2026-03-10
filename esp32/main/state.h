#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "host/ble_hs.h"
#include "sdkconfig.h"

#define DEVICE_ID_MAX_LEN 64
typedef struct {
    uint64_t timestamp_ns;
    int32_t value_uv;
} ecg_sample_t;

typedef struct {
    uint64_t timestamp_ns;
    int16_t x_mg;
    int16_t y_mg;
    int16_t z_mg;
} acc_sample_t;

extern char g_target_device_name[DEVICE_ID_MAX_LEN];
extern char g_device_id[DEVICE_ID_MAX_LEN];
extern char g_esp_id[32];
extern bool g_has_persisted_config;
extern bool g_config_required;
extern int g_ecg_sample_rate_hz;
extern int g_acc_sample_rate_hz;

extern uint8_t g_own_addr_type;
extern ble_addr_t g_target_addr;
extern uint16_t g_conn_handle;

extern bool g_connecting;
extern bool g_connected;
extern bool g_scanner_active;
extern uint32_t g_scanner_request_id;
extern uint32_t g_scan_duration_ms;
extern char g_scan_name_prefix[33];

extern uint16_t g_pmd_start;
extern uint16_t g_pmd_end;
extern uint16_t g_pmd_ctrl_handle;
extern uint16_t g_pmd_data_handle;
extern uint16_t g_pmd_cccd_handle;
extern uint16_t g_pmd_ctrl_cccd_handle;
extern uint8_t g_ecg_pmd_type;
extern uint8_t g_acc_pmd_type;
extern uint8_t g_ecg_settings_len;
extern uint8_t g_acc_settings_len;
extern uint16_t g_ecg_rate_selected;
extern uint16_t g_ecg_resolution_selected;
extern uint16_t g_acc_rate_selected;
extern uint16_t g_acc_resolution_selected;
extern uint16_t g_acc_range_selected;

extern uint32_t g_notification_count;
extern TickType_t g_last_command_time;
extern uint32_t g_usb_seq;

extern int g_ecg_count;
extern int g_acc_count;

extern uint32_t g_ecg_packet_count;
extern uint32_t g_acc_packet_count;
extern uint32_t g_total_ecg_samples;
extern uint32_t g_total_acc_samples;
extern TickType_t g_first_sample_time;

extern bool g_ecg_started;
extern bool g_acc_started;

extern uint32_t g_conn_interval_ms;
extern uint32_t g_current_mtu;

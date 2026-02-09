#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "host/ble_hs.h"
#include "sdkconfig.h"

#define DEVICE_ID_MAX_LEN 64
#define MAX_POLAR_LINKS 2
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

typedef struct {
    bool in_use;
    char target_device_name[DEVICE_ID_MAX_LEN];
    ble_addr_t target_addr;
    bool connecting;
    bool connected;
    uint16_t conn_handle;

    uint16_t pmd_start;
    uint16_t pmd_end;
    uint16_t pmd_ctrl_handle;
    uint16_t pmd_data_handle;
    uint16_t pmd_cccd_handle;
    uint16_t pmd_ctrl_cccd_handle;
    bool ctrl_cccd_enabled;
    bool data_cccd_enabled;
    bool waiting_ecg_settings;

    uint8_t ecg_settings_len;
    uint8_t acc_settings_len;
    uint16_t ecg_rate_selected;
    uint16_t ecg_resolution_selected;
    uint16_t acc_rate_selected;
    uint16_t acc_resolution_selected;
    uint16_t acc_range_selected;
    bool ecg_rate_warned;
    bool acc_rate_warned;

    bool ecg_started;
    bool acc_started;

    int ecg_sample_rate_hz;
    int acc_sample_rate_hz;

    uint32_t ecg_packet_count;
    uint32_t acc_packet_count;
    uint32_t total_ecg_samples;
    uint32_t total_acc_samples;
    int ecg_count;
    int acc_count;
    TickType_t first_sample_time;
} polar_link_t;

extern polar_link_t g_links[MAX_POLAR_LINKS];
extern char g_esp_id[32];
extern bool g_has_persisted_config;
extern bool g_config_required;
extern int g_default_ecg_sample_rate_hz;
extern int g_default_acc_sample_rate_hz;

extern uint8_t g_own_addr_type;
extern uint8_t g_ecg_pmd_type;
extern uint8_t g_acc_pmd_type;

extern uint32_t g_notification_count;
extern TickType_t g_last_command_time;
extern uint32_t g_usb_seq;

// Link-level counters moved into g_links[]

extern uint32_t g_conn_interval_ms;
extern uint32_t g_current_mtu;

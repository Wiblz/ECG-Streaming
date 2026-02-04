#include "state.h"

#include "host/ble_hs.h"

char g_target_device_name[DEVICE_ID_MAX_LEN];
char g_device_id[DEVICE_ID_MAX_LEN];
char g_esp_id[32];
bool g_has_persisted_config = false;
bool g_config_required = true;
int g_ecg_sample_rate_hz = CONFIG_ECG_SAMPLE_RATE;
int g_acc_sample_rate_hz = CONFIG_ACC_SAMPLE_RATE;

uint8_t g_own_addr_type;
ble_addr_t g_target_addr;
uint16_t g_conn_handle = BLE_HS_CONN_HANDLE_NONE;

bool g_connecting = false;
bool g_connected = false;

uint16_t g_pmd_start = 0;
uint16_t g_pmd_end = 0;
uint16_t g_pmd_ctrl_handle = 0;
uint16_t g_pmd_data_handle = 0;
uint16_t g_pmd_cccd_handle = 0;
uint16_t g_pmd_ctrl_cccd_handle = 0;
uint8_t g_ecg_pmd_type = 0x00;
uint8_t g_acc_pmd_type = 0x02;
uint8_t g_ecg_settings_len = 0;
uint8_t g_acc_settings_len = 0;
uint16_t g_ecg_rate_selected = 0;
uint16_t g_ecg_resolution_selected = 0;
uint16_t g_acc_rate_selected = 0;
uint16_t g_acc_resolution_selected = 0;
uint16_t g_acc_range_selected = 0;

uint32_t g_notification_count = 0;
TickType_t g_last_command_time = 0;
uint32_t g_usb_seq = 0;

int g_ecg_count = 0;
int g_acc_count = 0;

uint32_t g_ecg_packet_count = 0;
uint32_t g_acc_packet_count = 0;
uint32_t g_total_ecg_samples = 0;
uint32_t g_total_acc_samples = 0;
TickType_t g_first_sample_time = 0;

bool g_ecg_started = false;
bool g_acc_started = false;

uint32_t g_conn_interval_ms = 0;
uint32_t g_current_mtu = 0;

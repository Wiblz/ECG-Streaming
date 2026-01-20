#include "state.h"

char g_target_device_name[DEVICE_ID_MAX_LEN] = {0};
char g_device_id[DEVICE_ID_MAX_LEN] = {0};
char g_esp_id[32] = {0};
bool g_has_persisted_config = false;
bool g_config_required = true;
int g_ecg_sample_rate_hz = CONFIG_ECG_SAMPLE_RATE;
int g_acc_sample_rate_hz = CONFIG_ACC_SAMPLE_RATE;
int g_ecg_batch_size = CONFIG_ECG_BATCH_SIZE;
int g_acc_batch_size = CONFIG_ACC_BATCH_SIZE;

uint8_t g_own_addr_type = 0;
ble_addr_t g_target_addr = {0};
uint16_t g_conn_handle = BLE_HS_CONN_HANDLE_NONE;

bool g_connecting = false;
bool g_connected = false;

uint16_t g_pmd_start = 0;
uint16_t g_pmd_end = 0;
uint16_t g_pmd_ctrl_handle = 0;
uint16_t g_pmd_data_handle = 0;
uint16_t g_pmd_cccd_handle = 0;

uint32_t g_notification_count = 0;
TickType_t g_last_command_time = 0;

ecg_sample_t g_ecg_buffer[MAX_ECG_SAMPLES] = {0};
acc_sample_t g_acc_buffer[MAX_ACC_SAMPLES] = {0};
int g_ecg_count = 0;
int g_acc_count = 0;

uint32_t g_ecg_packet_count = 0;
uint32_t g_acc_packet_count = 0;
uint32_t g_total_ecg_samples = 0;
uint32_t g_total_acc_samples = 0;
TickType_t g_first_sample_time = 0;

bool g_ecg_started = false;
bool g_acc_started = false;

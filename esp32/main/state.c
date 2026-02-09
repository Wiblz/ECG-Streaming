#include "state.h"

#include "host/ble_hs.h"

polar_link_t g_links[MAX_POLAR_LINKS];
char g_esp_id[32];
bool g_has_persisted_config = false;
bool g_config_required = true;
int g_default_ecg_sample_rate_hz = CONFIG_ECG_SAMPLE_RATE;
int g_default_acc_sample_rate_hz = CONFIG_ACC_SAMPLE_RATE;

uint8_t g_own_addr_type;

uint8_t g_ecg_pmd_type = 0x00;
uint8_t g_acc_pmd_type = 0x02;

uint32_t g_notification_count = 0;
TickType_t g_last_command_time = 0;
uint32_t g_usb_seq = 0;

uint32_t g_conn_interval_ms = 0;
uint32_t g_current_mtu = 0;

#pragma once

#include <stdbool.h>
#include <stdint.h>

void ble_init(void);
int start_scan(void);
void ble_apply_updated_config(bool changed);
void ble_start_scan_request(uint32_t request_id, uint32_t duration_ms, const char *name_prefix);
void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle);
void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle);
void ble_schedule_start_acc(void);
void ble_schedule_read_battery(void);

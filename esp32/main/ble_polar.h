#pragma once

#include <stdint.h>

void ble_init(void);
int start_scan(void);
void pmd_start_ecg(uint16_t conn_handle, uint16_t ctrl_handle);
void pmd_start_acc(uint16_t conn_handle, uint16_t ctrl_handle);

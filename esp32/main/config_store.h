#pragma once

#include <stdbool.h>

void config_store_init(void);
void persist_usb_config_to_nvs(void);
void apply_runtime_config(void);
bool has_target_device(void);

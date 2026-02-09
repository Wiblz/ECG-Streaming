#include "config_store.h"

#include <stdio.h>
#include <string.h>

#include "esp_mac.h"
#include "esp_system.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "state.h"

static void format_esp_id(char *out, size_t out_len) {
    uint8_t mac[6] = {0};
    esp_efuse_mac_get_default(mac);
    snprintf(out, out_len, "%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static void load_usb_config_from_nvs(void) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open("ecg_usb", NVS_READONLY, &handle);
    if (err != ESP_OK) {
        return;
    }

    size_t len = sizeof(g_links[0].target_device_name);
    if (nvs_get_str(handle, "target_name", g_links[0].target_device_name, &len) == ESP_OK) {
        g_has_persisted_config = true;
    }

    int32_t value = 0;
    if (nvs_get_i32(handle, "ecg_rate", &value) == ESP_OK && value > 0) {
        g_links[0].ecg_sample_rate_hz = value;
    }
    if (nvs_get_i32(handle, "acc_rate", &value) == ESP_OK && value > 0) {
        g_links[0].acc_sample_rate_hz = value;
    }
    nvs_close(handle);
}

void persist_usb_config_to_nvs(void) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open("ecg_usb", NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return;
    }

    nvs_set_str(handle, "target_name", g_links[0].target_device_name);
    nvs_set_i32(handle, "ecg_rate", g_links[0].ecg_sample_rate_hz);
    nvs_set_i32(handle, "acc_rate", g_links[0].acc_sample_rate_hz);
    nvs_commit(handle);
    nvs_close(handle);
    g_has_persisted_config = true;
}

static int normalize_ecg_rate(int rate) {
    if (rate == 0) {
        return 0; // special value to disable ECG
    }
    if (rate == 130) {
        return rate;
    }
    return 130;
}

static int normalize_acc_rate(int rate) {
    if (rate == 0) {
        return 0; // special value to disable accelerometer
    }
    switch (rate) {
        case 25:
        case 50:
        case 100:
        case 200:
            return rate;
        default:
            return 100;
    }
}

void apply_runtime_config(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        g_links[i].ecg_sample_rate_hz = normalize_ecg_rate(g_links[i].ecg_sample_rate_hz);
        g_links[i].acc_sample_rate_hz = normalize_acc_rate(g_links[i].acc_sample_rate_hz);

        if (g_links[i].target_device_name[0] == '\0') {
            g_links[i].target_device_name[0] = '\0';
        }
        g_links[i].in_use = g_links[i].target_device_name[0] != '\0';
    }
}

bool has_target_device(void) {
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        if (g_links[i].target_device_name[0] != '\0') {
            return true;
        }
    }
    return false;
}

void config_store_init(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    memset(g_links, 0, sizeof(g_links));
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        g_links[i].ecg_sample_rate_hz = g_default_ecg_sample_rate_hz;
        g_links[i].acc_sample_rate_hz = g_default_acc_sample_rate_hz;
    }
    format_esp_id(g_esp_id, sizeof(g_esp_id));

#ifdef CONFIG_ALLOW_USB_CONFIG_PERSIST
    load_usb_config_from_nvs();
    apply_runtime_config();
    g_config_required = !g_has_persisted_config || !has_target_device();
#else
    // Persistence disabled - always require config from collector
    g_has_persisted_config = false;
    apply_runtime_config();
    g_config_required = true;
#endif
}

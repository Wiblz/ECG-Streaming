#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_collector.pb.h"

void usb_identity_task(void *param);
void usb_rx_task(void *param);
void usb_send_device_info_update(void);
void usb_send_ble_scan_result(
    uint32_t request_id,
    const ecg_streaming_BleScanSighting *sightings,
    size_t sighting_count,
    uint32_t duration_ms
);

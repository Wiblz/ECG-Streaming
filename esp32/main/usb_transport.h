#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_collector.pb.h"

void usb_transport_init(void);
bool usb_send_esp_message(const ecg_streaming_EspMessage *msg);
bool usb_send_esp_discovery_message(const ecg_streaming_EspDiscoveryMessage *msg);
bool usb_receive_collector_to_esp_message(ecg_streaming_CollectorToEspMessage *out_msg);

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ecg_streaming.pb.h"

void usb_transport_init(void);
bool usb_send_collector_message(const ecg_streaming_CollectorMessage *msg);
bool usb_receive_aggregator_message(ecg_streaming_AggregatorMessage *out_msg);

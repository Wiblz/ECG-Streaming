#pragma once

#include <stdbool.h>

#include "ecg_streaming.pb.h"

bool usb_send_collector_message(const ecg_streaming_CollectorMessage *msg);
bool usb_receive_aggregator_message(ecg_streaming_AggregatorMessage *out_msg);

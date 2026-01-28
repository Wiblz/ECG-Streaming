#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_collector.pb.h"

void output_sensor_frame(
    ecg_streaming_SensorType sensor_type,
    int32_t sample_rate,
    uint64_t polar_clock_us,
    const uint8_t *data,
    size_t len
);

#include "usb_output.h"

#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "pb.h"
#include "pb_encode.h"
#include "common.pb.h"
#include "esp_collector.pb.h"
#include "state.h"
#include "usb_transport.h"
#include "pb_helpers.h"

static const char *TAG = "H10_COMBINED";

static ecg_streaming_SensorFrame g_sensor_frame;
static ecg_streaming_EspMessage g_esp_msg;
static uint8_t g_sensor_data_buf[512];

void output_sensor_frame(
    ecg_streaming_SensorType sensor_type,
    int32_t sample_rate,
    uint64_t polar_clock_us,
    const uint8_t *data,
    size_t len
) {
    if (len > sizeof(g_sensor_data_buf)) {
        ESP_LOGE(TAG, "Sensor frame too large: %zu bytes", len);
        return;
    }

    // Copy data to our buffer
    memcpy(g_sensor_data_buf, data, len);

    bytes_view_t view = {
        .data = g_sensor_data_buf,
        .len = len,
    };

    g_sensor_frame = (ecg_streaming_SensorFrame)ecg_streaming_SensorFrame_init_zero;
    g_esp_msg = (ecg_streaming_EspMessage)ecg_streaming_EspMessage_init_zero;

    strlcpy(g_sensor_frame.device_id, g_device_id, sizeof(g_sensor_frame.device_id));

    // Sensor type
    g_sensor_frame.sensor_type = sensor_type;

    // Polar device clock (microseconds since Polar boot)
    g_sensor_frame.polar_clock_us = polar_clock_us;

    // Receiver device clock (microseconds since ESP32 boot)
    g_sensor_frame.receiver_clock_us = (uint64_t)esp_timer_get_time();

    // Sample rate
    g_sensor_frame.sample_rate = sample_rate;

    // Set up callback for raw data
    g_sensor_frame.raw_data.funcs.encode = pb_encode_bytes_cb;
    g_sensor_frame.raw_data.arg = (void *)&view;

    g_esp_msg.which_message = ecg_streaming_EspMessage_sensor_frame_tag;
    g_esp_msg.message.sensor_frame = g_sensor_frame;

    if (!usb_send_esp_message(&g_esp_msg)) {
        ESP_LOGE(TAG, "Failed to send sensor frame (type=%d)", sensor_type);
    }
}

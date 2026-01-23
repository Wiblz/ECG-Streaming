#include "usb_output.h"

#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "ecg_streaming.pb.h"
#include "state.h"
#include "usb_transport.h"

static const char *TAG = "H10_COMBINED";

#if BINARY_OUTPUT_MODE
static ecg_streaming_ECGSampleBatch g_ecg_batch;
static ecg_streaming_AccelerometerSampleBatch g_acc_batch;
static ecg_streaming_CollectorMessage g_collector_msg;
#endif

void output_ecg_binary(void) {
    if (g_ecg_count == 0) return;

#if BINARY_OUTPUT_MODE
    g_ecg_batch = (ecg_streaming_ECGSampleBatch)ecg_streaming_ECGSampleBatch_init_zero;
    g_collector_msg = (ecg_streaming_CollectorMessage)ecg_streaming_CollectorMessage_init_zero;

    strlcpy(g_ecg_batch.device_id, g_device_id, sizeof(g_ecg_batch.device_id));
    g_ecg_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    g_ecg_batch.samples_count = (pb_size_t)g_ecg_count;

    for (int i = 0; i < g_ecg_count; i++) {
        ecg_streaming_ECGSample *sample = &g_ecg_batch.samples[i];
        sample->device_timestamp_us = (double)(g_ecg_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->raw_value = g_ecg_buffer[i].value_uv;
        sample->sample_rate = g_ecg_sample_rate_hz;
    }

    g_collector_msg.which_message = ecg_streaming_CollectorMessage_ecg_batch_tag;
    g_collector_msg.message.ecg_batch = g_ecg_batch;

    if (!usb_send_collector_message(&g_collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ECG batch");
    }
#endif

    g_ecg_count = 0;
}

void output_acc_binary(void) {
    if (g_acc_count == 0) return;

#if BINARY_OUTPUT_MODE
    g_acc_batch = (ecg_streaming_AccelerometerSampleBatch)ecg_streaming_AccelerometerSampleBatch_init_zero;
    g_collector_msg = (ecg_streaming_CollectorMessage)ecg_streaming_CollectorMessage_init_zero;

    strlcpy(g_acc_batch.device_id, g_device_id, sizeof(g_acc_batch.device_id));
    g_acc_batch.batch_timestamp_ms = (int64_t)(esp_timer_get_time() / 1000);
    g_acc_batch.samples_count = (pb_size_t)g_acc_count;

    for (int i = 0; i < g_acc_count; i++) {
        ecg_streaming_AccelerometerSample *sample = &g_acc_batch.samples[i];
        sample->device_timestamp_us = (double)(g_acc_buffer[i].timestamp_ns / 1000);
        sample->host_receive_time_s = 0.0;
        sample->x = (float)g_acc_buffer[i].x_mg / 1000.0f;
        sample->y = (float)g_acc_buffer[i].y_mg / 1000.0f;
        sample->z = (float)g_acc_buffer[i].z_mg / 1000.0f;
        sample->sample_rate = g_acc_sample_rate_hz;
    }

    g_collector_msg.which_message = ecg_streaming_CollectorMessage_acc_batch_tag;
    g_collector_msg.message.acc_batch = g_acc_batch;

    if (!usb_send_collector_message(&g_collector_msg)) {
        ESP_LOGE(TAG, "Failed to send ACC batch");
    }
#endif

    g_acc_count = 0;
}

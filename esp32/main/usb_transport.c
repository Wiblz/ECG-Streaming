#include "usb_transport.h"

#include <stdio.h>

#include "pb.h"
#include "pb_decode.h"
#include "pb_encode.h"

#include "state.h"

static uint8_t g_frame_buf[4096];
static uint8_t g_payload_buf[4096];
static uint8_t g_rx_frame_buf[4096];
static uint8_t g_rx_payload_buf[2048];
static ecg_streaming_UsbFrame g_usb_frame;

typedef struct {
    const uint8_t *data;
    size_t len;
} bytes_view_t;

typedef struct {
    uint8_t *data;
    size_t max_len;
    size_t len;
} bytes_sink_t;

static uint32_t crc32_ieee(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

static bool encode_bytes_cb(pb_ostream_t *stream, const pb_field_t *field, void *const *arg) {
    const bytes_view_t *view = (const bytes_view_t *)(*arg);
    if (!pb_encode_tag_for_field(stream, field)) {
        return false;
    }
    return pb_encode_string(stream, view->data, view->len);
}

static bool decode_bytes_cb(pb_istream_t *stream, const pb_field_t *field, void **arg) {
    bytes_sink_t *sink = (bytes_sink_t *)(*arg);
    size_t len = stream->bytes_left;
    if (len > sink->max_len) {
        return false;
    }
    if (!pb_read(stream, sink->data, len)) {
        return false;
    }
    sink->len = len;
    return true;
}

static bool send_usb_frame(ecg_streaming_UsbPayloadType type,
                           const uint8_t *payload, size_t payload_len) {
    bytes_view_t view = {
        .data = payload,
        .len = payload_len,
    };

    g_usb_frame = (ecg_streaming_UsbFrame)ecg_streaming_UsbFrame_init_zero;
    g_usb_frame.version = 1;
    g_usb_frame.payload_type = type;
    g_usb_frame.seq = g_usb_seq++;
    g_usb_frame.crc32 = crc32_ieee(payload, payload_len);
    g_usb_frame.payload.funcs.encode = encode_bytes_cb;
    g_usb_frame.payload.arg = (void *)&view;

    pb_ostream_t stream = pb_ostream_from_buffer(g_frame_buf, sizeof(g_frame_buf));
    if (!pb_encode(&stream, ecg_streaming_UsbFrame_fields, &g_usb_frame)) {
        return false;
    }

    uint32_t frame_len = (uint32_t)stream.bytes_written;
    uint8_t len_le[4] = {
        (uint8_t)(frame_len & 0xFF),
        (uint8_t)((frame_len >> 8) & 0xFF),
        (uint8_t)((frame_len >> 16) & 0xFF),
        (uint8_t)((frame_len >> 24) & 0xFF),
    };

    fwrite(len_le, 1, sizeof(len_le), stdout);
    fwrite(g_frame_buf, 1, frame_len, stdout);
    fflush(stdout);
    return true;
}

void usb_transport_init(void) {
    g_usb_frame = (ecg_streaming_UsbFrame)ecg_streaming_UsbFrame_init_zero;
}

bool usb_send_collector_message(const ecg_streaming_CollectorMessage *msg) {
    pb_ostream_t stream = pb_ostream_from_buffer(g_payload_buf, sizeof(g_payload_buf));

    if (!pb_encode(&stream, ecg_streaming_CollectorMessage_fields, msg)) {
        return false;
    }

    return send_usb_frame(ecg_streaming_UsbPayloadType_USB_PAYLOAD_TYPE_COLLECTOR_MESSAGE,
                          g_payload_buf, stream.bytes_written);
}

bool usb_receive_aggregator_message(ecg_streaming_AggregatorMessage *out_msg) {
    uint8_t len_le[4];
    if (fread(len_le, 1, sizeof(len_le), stdin) != sizeof(len_le)) {
        return false;
    }

    uint32_t frame_len = (uint32_t)len_le[0] |
                         ((uint32_t)len_le[1] << 8) |
                         ((uint32_t)len_le[2] << 16) |
                         ((uint32_t)len_le[3] << 24);

    if (frame_len == 0 || frame_len > sizeof(g_rx_frame_buf)) {
        return false;
    }

    if (fread(g_rx_frame_buf, 1, frame_len, stdin) != frame_len) {
        return false;
    }

    ecg_streaming_UsbFrame frame = ecg_streaming_UsbFrame_init_zero;
    bytes_sink_t sink = {
        .data = g_rx_payload_buf,
        .max_len = sizeof(g_rx_payload_buf),
        .len = 0,
    };
    frame.payload.funcs.decode = decode_bytes_cb;
    frame.payload.arg = &sink;

    pb_istream_t stream = pb_istream_from_buffer(g_rx_frame_buf, frame_len);
    if (!pb_decode(&stream, ecg_streaming_UsbFrame_fields, &frame)) {
        return false;
    }

    if (sink.len == 0) {
        return false;
    }

    uint32_t computed_crc = crc32_ieee(sink.data, sink.len);
    if (computed_crc != frame.crc32) {
        return false;
    }

    if (frame.payload_type != ecg_streaming_UsbPayloadType_USB_PAYLOAD_TYPE_AGGREGATOR_MESSAGE) {
        return false;
    }

    pb_istream_t payload_stream = pb_istream_from_buffer(sink.data, sink.len);
    if (!pb_decode(&payload_stream, ecg_streaming_AggregatorMessage_fields, out_msg)) {
        return false;
    }

    return true;
}

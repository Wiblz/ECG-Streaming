#pragma once

#include <stddef.h>
#include <stdint.h>

#include "pb.h"

typedef struct {
    const uint8_t *data;
    size_t len;
} bytes_view_t;

bool pb_encode_bytes_cb(pb_ostream_t *stream, const pb_field_t *field, void *const *arg);

#include "pb_helpers.h"

#include "pb_encode.h"

bool pb_encode_bytes_cb(pb_ostream_t *stream, const pb_field_t *field, void *const *arg) {
    const bytes_view_t *view = (const bytes_view_t *)(*arg);
    if (!pb_encode_tag_for_field(stream, field)) {
        return false;
    }
    return pb_encode_string(stream, view->data, view->len);
}

#pragma once

#include <stdbool.h>

void led_status_init(void);
void led_status_set_polar_connected(bool connected);
void led_status_mark_stream_activity(int link_index);

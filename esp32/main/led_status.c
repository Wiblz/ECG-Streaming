#include "led_status.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_rom_sys.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"

#include "state.h"

static const char *TAG = "LED_STATUS";

#define LED_PIN 21
#define NUM_LEDS 1

// Timing
static const uint32_t FRAME_MS = 15;
static const uint32_t STREAM_ACTIVE_MS = 1000;
static const uint32_t IDENTIFY_DURATION_MS = 3000;

// Brightness shaping (0..1)
static const float BRIGHTNESS = 0.08f;
static const float IDENTIFY_BRIGHTNESS = 0.22f;

typedef struct {
    uint8_t r;
    uint8_t g;
    uint8_t b;
} rgb_u8_t;

static const rgb_u8_t k_yellow = {255, 120, 0};
static const rgb_u8_t k_green = {0, 255, 0};
static const rgb_u8_t k_blue = {0, 0, 255};
static const rgb_u8_t k_cyan = {0, 255, 180};

static rmt_channel_handle_t s_tx_chan = NULL;
static rmt_encoder_handle_t s_encoder = NULL;
static uint8_t s_pixel_buf[NUM_LEDS * 3];
static volatile bool s_polar_connected = false;
static volatile TickType_t s_last_stream_tick = 0;
static volatile TickType_t s_identify_until_tick = 0;

void led_status_set_polar_connected(bool connected) {
    s_polar_connected = connected;
    if (!connected) {
        s_last_stream_tick = 0;
    }
}

void led_status_mark_stream_activity(void) {
    s_last_stream_tick = xTaskGetTickCount();
}

void led_status_trigger_identify(void) {
    s_identify_until_tick = xTaskGetTickCount() + pdMS_TO_TICKS(IDENTIFY_DURATION_MS);
}

static rgb_u8_t scale_color(rgb_u8_t c, float scale) {
    float rf = (float)c.r * scale;
    float gf = (float)c.g * scale;
    float bf = (float)c.b * scale;

    if (rf > 255.0f) rf = 255.0f;
    if (gf > 255.0f) gf = 255.0f;
    if (bf > 255.0f) bf = 255.0f;

    rgb_u8_t out = {
        .r = (uint8_t)roundf(rf),
        .g = (uint8_t)roundf(gf),
        .b = (uint8_t)roundf(bf),
    };
    return out;
}

static void set_led(rgb_u8_t c) {
    s_pixel_buf[0] = c.g;
    s_pixel_buf[1] = c.r;
    s_pixel_buf[2] = c.b;

    rmt_transmit_config_t tx_config = {
        .loop_count = 0,
        .flags.eot_level = 0,
        .flags.queue_nonblocking = 0,
    };
    rmt_transmit(s_tx_chan, s_encoder, s_pixel_buf, sizeof(s_pixel_buf), &tx_config);
    rmt_tx_wait_all_done(s_tx_chan, -1);
    esp_rom_delay_us(60);
}

static rgb_u8_t rainbow_color(uint32_t phase_ms) {
    // Run two full hue rotations over the identify window so the signal reads
    // as intentional motion rather than a slow color drift.
    uint32_t wheel = (phase_ms * 512u) / IDENTIFY_DURATION_MS;
    wheel &= 0xFFu;

    rgb_u8_t c = {0, 0, 0};
    if (wheel < 85u) {
        c.r = (uint8_t)(255u - wheel * 3u);
        c.g = (uint8_t)(wheel * 3u);
        c.b = 0;
    } else if (wheel < 170u) {
        wheel -= 85u;
        c.r = 0;
        c.g = (uint8_t)(255u - wheel * 3u);
        c.b = (uint8_t)(wheel * 3u);
    } else {
        wheel -= 170u;
        c.r = (uint8_t)(wheel * 3u);
        c.g = 0;
        c.b = (uint8_t)(255u - wheel * 3u);
    }

    return scale_color(c, IDENTIFY_BRIGHTNESS);
}

static void led_task(void *param) {
    while (1) {
        TickType_t now_tick = xTaskGetTickCount();
        uint32_t now_ms = now_tick * portTICK_PERIOD_MS;
        uint32_t since_stream_ms = (uint32_t)(now_tick - s_last_stream_tick) * portTICK_PERIOD_MS;
        bool streaming_active = s_polar_connected &&
                                s_last_stream_tick != 0 &&
                                since_stream_ms < STREAM_ACTIVE_MS;
        bool polar_connected = s_polar_connected;
        bool scanner_active = g_scanner_active;
        bool identify_active = s_identify_until_tick != 0 && now_tick < s_identify_until_tick;

        rgb_u8_t c = {0, 0, 0};

        if (identify_active) {
            TickType_t remaining_ticks = s_identify_until_tick - now_tick;
            uint32_t elapsed_ms = IDENTIFY_DURATION_MS - (remaining_ticks * portTICK_PERIOD_MS);
            c = rainbow_color(elapsed_ms);
        } else if (streaming_active) {
            // Streaming: solid green (data received in last 500ms)
            c = scale_color(k_green, BRIGHTNESS);
        } else if (polar_connected) {
            // Connected but no recent data: blink green every 1000ms
            uint32_t t = now_ms % 1000;
            if (t < 100) {
                c = scale_color(k_green, BRIGHTNESS);
            }
        } else if (scanner_active) {
            // Scanner mode: two short cyan pulses every 700ms
            uint32_t t = now_ms % 700;
            if ((t < 70) || (t >= 140 && t < 210)) {
                c = scale_color(k_cyan, BRIGHTNESS);
            }
        } else if (!g_config_required) {
            // Configured but not connected: solid blue
            c = scale_color(k_blue, BRIGHTNESS);
        } else {
            // Not configured: blink yellow every 500ms
            uint32_t t = now_ms % 500;
            if (t < 80) {
                c = scale_color(k_yellow, BRIGHTNESS);
            }
        }

        set_led(c);

        vTaskDelay(pdMS_TO_TICKS(FRAME_MS));
    }
}

void led_status_init(void) {
    rmt_tx_channel_config_t tx_chan_config = {
        .gpio_num = LED_PIN,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .mem_block_symbols = 64,
        .trans_queue_depth = 1,
        .intr_priority = 0,
        .flags.invert_out = false,
        .flags.with_dma = false,
        .flags.io_loop_back = false,
        .flags.io_od_mode = false,
        .flags.allow_pd = false,
        .flags.init_level = 0,
    };

    esp_err_t rc = rmt_new_tx_channel(&tx_chan_config, &s_tx_chan);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "RMT channel init failed: %d", rc);
        return;
    }

    rmt_bytes_encoder_config_t bytes_config = {
        .bit0 = {
            .level0 = 1,
            .duration0 = 4,
            .level1 = 0,
            .duration1 = 8,
        },
        .bit1 = {
            .level0 = 1,
            .duration0 = 8,
            .level1 = 0,
            .duration1 = 6,
        },
        .flags.msb_first = 1,
    };

    rc = rmt_new_bytes_encoder(&bytes_config, &s_encoder);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "RMT encoder init failed: %d", rc);
        return;
    }

    rc = rmt_enable(s_tx_chan);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "RMT enable failed: %d", rc);
        return;
    }

    memset(s_pixel_buf, 0, sizeof(s_pixel_buf));
    s_last_stream_tick = 0;
    xTaskCreate(led_task, "led_status", 3072, NULL, tskIDLE_PRIORITY + 1, NULL);
}

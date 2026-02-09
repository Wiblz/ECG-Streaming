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

// Brightness shaping (0..1)
static const float BRIGHTNESS = 0.08f;

typedef struct {
    uint8_t r;
    uint8_t g;
    uint8_t b;
} rgb_u8_t;

static const rgb_u8_t k_yellow = {255, 120, 0};
static const rgb_u8_t k_green = {0, 255, 0};
static const rgb_u8_t k_blue = {0, 0, 255};
static const rgb_u8_t k_cyan = {0, 255, 255};

static rmt_channel_handle_t s_tx_chan = NULL;
static rmt_encoder_handle_t s_encoder = NULL;
static uint8_t s_pixel_buf[NUM_LEDS * 3];
static volatile bool s_polar_connected = false;
static volatile TickType_t s_last_stream_tick[MAX_POLAR_LINKS] = {0};

void led_status_set_polar_connected(bool connected) {
    s_polar_connected = connected;
    if (!connected) {
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            s_last_stream_tick[i] = 0;
        }
    }
}

void led_status_mark_stream_activity(int link_index) {
    if (link_index < 0 || link_index >= MAX_POLAR_LINKS) {
        return;
    }
    s_last_stream_tick[link_index] = xTaskGetTickCount();
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

static void led_task(void *param) {
    while (1) {
        uint32_t now_ms = xTaskGetTickCount() * portTICK_PERIOD_MS;
        int active_streams = 0;
        int connected_streams = 0;
        for (int i = 0; i < MAX_POLAR_LINKS; i++) {
            if (g_links[i].connected) {
                connected_streams++;
            }
            if (s_last_stream_tick[i] != 0) {
                uint32_t since_stream_ms =
                    (uint32_t)(xTaskGetTickCount() - s_last_stream_tick[i]) *
                    portTICK_PERIOD_MS;
                if (since_stream_ms < STREAM_ACTIVE_MS) {
                    active_streams++;
                }
            }
        }
        bool polar_connected = s_polar_connected || connected_streams > 0;

        rgb_u8_t c = {0, 0, 0};

        if (active_streams >= 2) {
            // Streaming from two Polars: solid cyan
            c = scale_color(k_cyan, BRIGHTNESS);
        } else if (active_streams == 1) {
            // Streaming from one Polar: solid green
            c = scale_color(k_green, BRIGHTNESS);
        } else if (polar_connected) {
            // Connected but no recent data: blink green every 1000ms
            uint32_t t = now_ms % 1000;
            if (t < 100) {
                c = scale_color(k_green, BRIGHTNESS);
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
    for (int i = 0; i < MAX_POLAR_LINKS; i++) {
        s_last_stream_tick[i] = 0;
    }
    xTaskCreate(led_task, "led_status", 3072, NULL, tskIDLE_PRIORITY + 1, NULL);
}

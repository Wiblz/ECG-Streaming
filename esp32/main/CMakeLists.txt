idf_component_register(
    SRCS "main.c" "state.c" "config_store.c" "usb_transport.c" "usb_provision.c" "usb_output.c" "usb_cdc.c" "ble_polar.c" "pb_helpers.c"
    INCLUDE_DIRS "."
    REQUIRES ecg_proto nanopb nvs_flash bt esp_timer esp_tinyusb
)

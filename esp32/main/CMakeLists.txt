idf_component_register(
    SRCS
        "main.c"
        "state.c"
        "config_store.c"
        "usb_transport.c"
        "usb_provision.c"
        "ble_polar.c"
    INCLUDE_DIRS "."
    REQUIRES ecg_proto nanopb nvs_flash bt esp_timer
)

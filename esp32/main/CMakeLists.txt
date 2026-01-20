idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES ecg_proto nanopb nvs_flash bt esp_timer
)

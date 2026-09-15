set(requires
    driver
    esp_driver_i2c
    esp_driver_i2s
    esp_timer
    esp_wifi
    esp_netif
    esp_event
    nvs_flash
    esp_http_client
    tcp_transport
    json
    )

idf_component_register(SRCS
                       main.cc
                       bsp_board.cc
                       servo_controller.cc
                       pca9685_controller.cc
                       robot_motions.cc
                       touch_inputs.cc
                       wifi_manager.cc
                       audio_recorder.cc
                       ai_client.cc
                       audio_reply_player.cc
                       voice_trace.cc
                       INCLUDE_DIRS
                       "."
                       REQUIRES
                       ${requires}
                       )

# Observe upload body write completion without replacing esp_http_client_perform.
target_link_options(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_transport_write")

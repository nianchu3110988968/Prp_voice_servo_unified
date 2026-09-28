#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
typedef int i2c_port_t;
static constexpr i2c_port_t I2C_NUM_0 = 0;
static constexpr int I2C_MODE_MASTER = 1;
struct i2c_config_t {
    int mode;
    int sda_io_num;
    int scl_io_num;
    int sda_pullup_en;
    int scl_pullup_en;
    struct { uint32_t clk_speed; } master;
};
esp_err_t i2c_param_config(i2c_port_t, const i2c_config_t *);
esp_err_t i2c_driver_install(i2c_port_t, int, size_t, size_t, int);
esp_err_t i2c_master_write_to_device(i2c_port_t, uint8_t, const uint8_t *, size_t, TickType_t);
esp_err_t i2c_master_write_read_device(i2c_port_t, uint8_t, const uint8_t *, size_t, uint8_t *, size_t, TickType_t);

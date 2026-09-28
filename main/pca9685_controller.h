#pragma once

#include <stdint.h>

#include "esp_err.h"
#include "robot_config.h"

class Pca9685Controller {
public:
    esp_err_t init();
    esp_err_t setOutputsEnabled(bool enabled, uint16_t channel_mask = 0xFFFF);
    esp_err_t writeMicroseconds(uint8_t channel, int pulse_us);

private:
    esp_err_t writeChannel(uint8_t channel, uint16_t count, bool full_off);
    esp_err_t writeRegister(uint8_t reg, uint8_t value);
    esp_err_t readRegister(uint8_t reg, uint8_t *value);

    bool initialized_ = false;
    // RobotMotions serializes access to this driver with its output mutex.
    uint16_t enabled_channels_ = 0;
    uint16_t pulse_counts_[16] = {}; // Zero means the channel is not configured.
};

#pragma once

#include <stdint.h>

#include "esp_err.h"
#include "robot_config.h"

class Pca9685Controller {
public:
    esp_err_t init();
    esp_err_t writeMicroseconds(uint8_t channel, int pulse_us);

private:
    esp_err_t writeRegister(uint8_t reg, uint8_t value);
    esp_err_t readRegister(uint8_t reg, uint8_t *value);

    bool initialized_ = false;
};

#include "pca9685_controller.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "pca9685";

static constexpr uint8_t PCA9685_ADDR = 0x40;
static constexpr uint8_t MODE1 = 0x00;
static constexpr uint8_t PRESCALE = 0xFE;
static constexpr uint8_t LED0_ON_L = 0x06;
static constexpr uint8_t ALL_LED_OFF_H = 0xFD;
static constexpr uint8_t FULL_OFF = 0x10;
static constexpr uint8_t RESTART = 0x80;
static constexpr uint8_t SLEEP = 0x10;
static constexpr uint8_t AI = 0x20;
static constexpr float SERVO_FREQ_HZ = 50.0f;

esp_err_t Pca9685Controller::init() {
    i2c_config_t conf = {};
    conf.mode = I2C_MODE_MASTER;
    conf.sda_io_num = ROBOT_I2C_SDA_PIN;
    conf.scl_io_num = ROBOT_I2C_SCL_PIN;
    conf.sda_pullup_en = GPIO_PULLUP_ENABLE;
    conf.scl_pullup_en = GPIO_PULLUP_ENABLE;
    conf.master.clk_speed = ROBOT_I2C_FREQ_HZ;

    esp_err_t ret = i2c_param_config(ROBOT_I2C_PORT, &conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "i2c_param_config failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = i2c_driver_install(ROBOT_I2C_PORT, conf.mode, 0, 0, 0);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "i2c_driver_install failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = writeRegister(MODE1, SLEEP);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "PCA9685 not responding at 0x%02x: %s", PCA9685_ADDR, esp_err_to_name(ret));
        return ret;
    }

    const float prescale_value = 25000000.0f / (4096.0f * SERVO_FREQ_HZ) - 1.0f;
    const uint8_t prescale = static_cast<uint8_t>(prescale_value + 0.5f);
    // ALL_LED registers broadcast into every channel register (datasheet 7.3.4).
    // Disable before restarting the oscillator, including after an ESP-only reset.
    ret = writeRegister(ALL_LED_OFF_H, FULL_OFF);
    if (ret != ESP_OK) return ret;
    ret = writeRegister(PRESCALE, prescale);
    if (ret != ESP_OK) return ret;
    ret = writeRegister(MODE1, AI);
    if (ret != ESP_OK) return ret;
    vTaskDelay(pdMS_TO_TICKS(5));
    ret = writeRegister(MODE1, RESTART | AI);
    if (ret != ESP_OK) return ret;

    initialized_ = true;
    enabled_channels_ = 0;
    ESP_LOGI(TAG, "PCA9685 initialized on SDA=%d SCL=%d", ROBOT_I2C_SDA_PIN, ROBOT_I2C_SCL_PIN);
    return ESP_OK;
}

esp_err_t Pca9685Controller::setOutputsEnabled(bool enabled, uint16_t channel_mask) {
    if (!initialized_) {
        return ESP_ERR_INVALID_STATE;
    }

    // Disable first, including when switching from a wider mask to a single servo.
    // Cached pulses from a prior session must never enable an unselected channel.
    enabled_channels_ = 0;
    esp_err_t ret = writeRegister(ALL_LED_OFF_H, FULL_OFF);
    if (ret != ESP_OK || !enabled) return ret;

    // Never clear ALL_LED_OFF_H globally: that overwrites the high count bits.
    // Restore complete per-channel values; unused channels remain FULL OFF.
    for (uint8_t channel = 0; channel < 16; ++channel) {
        const bool selected = (channel_mask & servoChannelMask(channel)) != 0;
        ret = writeChannel(channel, pulse_counts_[channel], !selected || pulse_counts_[channel] == 0);
        if (ret != ESP_OK) {
            esp_err_t stop_ret = writeRegister(ALL_LED_OFF_H, FULL_OFF);
            if (stop_ret != ESP_OK) {
                ESP_LOGE(TAG, "PWM shutdown also failed; disconnect servo power: %s", esp_err_to_name(stop_ret));
            }
            return ret;
        }
    }
    enabled_channels_ = channel_mask;
    return ESP_OK;
}

esp_err_t Pca9685Controller::writeMicroseconds(uint8_t channel, int pulse_us) {
    if (!initialized_) {
        return ESP_ERR_INVALID_STATE;
    }
    if (channel > 15) {
        return ESP_ERR_INVALID_ARG;
    }

    if (pulse_us < SERVO_US_MIN) {
        pulse_us = SERVO_US_MIN;
    } else if (pulse_us > SERVO_US_MAX) {
        pulse_us = SERVO_US_MAX;
    }

    const uint16_t off_count = static_cast<uint16_t>((pulse_us * 4096L) / 20000L);
    esp_err_t ret = writeChannel(channel, off_count, (enabled_channels_ & servoChannelMask(channel)) == 0);
    if (ret == ESP_OK) pulse_counts_[channel] = off_count;
    return ret;
}

esp_err_t Pca9685Controller::writeChannel(uint8_t channel, uint16_t off_count, bool full_off) {
    const uint8_t reg = LED0_ON_L + 4 * channel;
    uint8_t data[5] = {
        reg,
        0x00,
        0x00,
        static_cast<uint8_t>(off_count & 0xFF),
        static_cast<uint8_t>(((off_count >> 8) & 0x0F) | (full_off ? FULL_OFF : 0)),
    };

    return i2c_master_write_to_device(
        ROBOT_I2C_PORT, PCA9685_ADDR, data, sizeof(data), pdMS_TO_TICKS(100));
}

esp_err_t Pca9685Controller::writeRegister(uint8_t reg, uint8_t value) {
    uint8_t data[2] = {reg, value};
    return i2c_master_write_to_device(
        ROBOT_I2C_PORT, PCA9685_ADDR, data, sizeof(data), pdMS_TO_TICKS(100));
}

esp_err_t Pca9685Controller::readRegister(uint8_t reg, uint8_t *value) {
    return i2c_master_write_read_device(
        ROBOT_I2C_PORT, PCA9685_ADDR, &reg, 1, value, 1, pdMS_TO_TICKS(100));
}

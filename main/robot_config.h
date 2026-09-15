#pragma once

#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/i2c.h"

static constexpr i2c_port_t ROBOT_I2C_PORT = I2C_NUM_0;
static constexpr gpio_num_t ROBOT_I2C_SDA_PIN = GPIO_NUM_1;
static constexpr gpio_num_t ROBOT_I2C_SCL_PIN = GPIO_NUM_2;
static constexpr uint32_t ROBOT_I2C_FREQ_HZ = 100000;

// GPIO4/5/6 are reserved by INMP441 in the voice module.
static constexpr gpio_num_t TOUCH_1_PIN = GPIO_NUM_8;
static constexpr gpio_num_t TOUCH_2_PIN = GPIO_NUM_9;
static constexpr gpio_num_t TOUCH_3_PIN = GPIO_NUM_10;
// Keep disabled until the three touch inputs are physically connected and
// their active levels/debounce behavior have been verified.
static constexpr bool TOUCH_INPUTS_ENABLED = false;

// PCA9685 channel assignment for the four legs and tail.
static constexpr uint8_t SERVO_FRONT_LEFT = 0;
static constexpr uint8_t SERVO_FRONT_RIGHT = 1;
static constexpr uint8_t SERVO_REAR_LEFT = 2;
static constexpr uint8_t SERVO_REAR_RIGHT = 3;
static constexpr uint8_t SERVO_TAIL = 4;

static constexpr int SERVO_US_MIN = 500;
static constexpr int SERVO_US_MAX = 2500;
static constexpr uint8_t SERVO_STEP_DEGREES = 2;
static constexpr uint32_t SERVO_STEP_DELAY_MS = 12;

struct ServoLimit {
    uint8_t channel;
    int min_angle;
    int max_angle;
    int home_angle;
};

static constexpr ServoLimit SERVO_LIMITS[] = {
    // These conservative limits are for unloaded bench tests. Calibrate them
    // against the real linkage before increasing the motion range.
    {SERVO_FRONT_LEFT, 70, 110, 90},
    {SERVO_FRONT_RIGHT, 70, 110, 90},
    {SERVO_REAR_LEFT, 70, 110, 90},
    {SERVO_REAR_RIGHT, 70, 110, 90},
    {SERVO_TAIL, 60, 120, 90},
};

static constexpr size_t SERVO_LIMIT_COUNT = sizeof(SERVO_LIMITS) / sizeof(SERVO_LIMITS[0]);

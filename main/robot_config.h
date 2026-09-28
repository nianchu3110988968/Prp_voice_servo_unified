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

// 舵机接线唯一配置入口：填 PCA9685 通道号 0~15，不是 ESP32 GPIO。
// 初始化、串口部位名称和动作均使用此映射；改接线只修改这里并重新编译/烧录。
struct ServoChannelMap {
    int front_left;
    int front_right;
    int rear_left;
    int rear_right;
    int tail;
};
static constexpr ServoChannelMap SERVO_CHANNELS = {
    15, // 左前 fl
    11, // 右前 fr
    7,  // 左后 rl
    3,  // 右后 rr
    0,  // 尾部 tail
};

constexpr bool servoChannelsValid(const ServoChannelMap &map) {
    const int channels[] = {map.front_left, map.front_right, map.rear_left, map.rear_right, map.tail};
    for (size_t i = 0; i < 5; ++i) {
        if (channels[i] < 0 || channels[i] > 15) return false;
        for (size_t j = 0; j < i; ++j) {
            if (channels[i] == channels[j]) return false;
        }
    }
    return true;
}
static_assert(servoChannelsValid(SERVO_CHANNELS), "Servo channels must be unique PCA9685 outputs 0..15");
static constexpr uint8_t SERVO_FRONT_LEFT = SERVO_CHANNELS.front_left;
static constexpr uint8_t SERVO_FRONT_RIGHT = SERVO_CHANNELS.front_right;
static constexpr uint8_t SERVO_REAR_LEFT = SERVO_CHANNELS.rear_left;
static constexpr uint8_t SERVO_REAR_RIGHT = SERVO_CHANNELS.rear_right;
static constexpr uint8_t SERVO_TAIL = SERVO_CHANNELS.tail;

constexpr uint16_t servoChannelMask(uint8_t channel) {
    return channel < 16 ? static_cast<uint16_t>(1u << channel) : 0;
}
static constexpr uint16_t SERVO_ALL_CHANNEL_MASK =
    servoChannelMask(SERVO_FRONT_LEFT) | servoChannelMask(SERVO_FRONT_RIGHT) |
    servoChannelMask(SERVO_REAR_LEFT) | servoChannelMask(SERVO_REAR_RIGHT) |
    servoChannelMask(SERVO_TAIL);
// 单路调试仅允许 home +/- 5 度，不等于装机后的机械安全范围。
static constexpr int SERVO_DEBUG_SPAN_DEGREES = 5;

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
    // Array order is body order (fl/fr/rl/rr/tail), NOT physical channel order.
    // These conservative limits are for unloaded bench tests. Calibrate them
    // against the real linkage before increasing the motion range.
    {SERVO_FRONT_LEFT, 70, 110, 90},
    {SERVO_FRONT_RIGHT, 70, 110, 90},
    {SERVO_REAR_LEFT, 70, 110, 90},
    {SERVO_REAR_RIGHT, 70, 110, 90},
    {SERVO_TAIL, 60, 120, 90},
};

static constexpr size_t SERVO_LIMIT_COUNT = sizeof(SERVO_LIMITS) / sizeof(SERVO_LIMITS[0]);
static_assert(SERVO_LIMIT_COUNT == 5, "This robot has exactly five servos");

#pragma once

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "pca9685_controller.h"

class RobotMotions {
public:
    esp_err_t init();
    bool isReady() const;
    void setLogEnabled(bool enabled);
    void actionShy();
    void actionHappy();
    void actionCurious();
    void actionReset();
    void cancelPendingAndReset();
    bool requestServoAngle(uint8_t channel, int angle);

private:
    enum class CommandType : uint8_t {
        Reset,
        Shy,
        Happy,
        Curious,
        SetServo,
    };

    struct MotionCommand {
        CommandType type;
        uint8_t channel;
        int angle;
    };

    static void motionTaskEntry(void *arg);
    void motionTask();
    bool enqueueCommand(CommandType type, uint8_t channel = 0, int angle = 0);
    void executeCommand(const MotionCommand &command);
    void executeShy();
    void executeHappy();
    void executeCurious();
    void executeReset();
    void moveToPose(const int target_angles[SERVO_LIMIT_COUNT]);
    void setAngle(uint8_t channel, int angle);
    void writeServoAngle(uint8_t channel, int angle);
    int limitAngle(uint8_t channel, int angle) const;
    size_t servoIndex(uint8_t channel) const;
    const ServoLimit *findServoLimit(uint8_t channel) const;

    Pca9685Controller pwm_;
    QueueHandle_t command_queue_ = nullptr;
    int current_angles_[SERVO_LIMIT_COUNT] = {};
    bool ready_ = false;
    bool log_enabled_ = false;
};

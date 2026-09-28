#pragma once

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "pca9685_controller.h"

class RobotMotions {
public:
    esp_err_t init();
    esp_err_t enableOutputsAtHome();
    esp_err_t enableSingleServoAtHome(uint8_t channel);
    esp_err_t disableOutputs();
    bool isReady() const;
    void setLogEnabled(bool enabled);
    void actionShy();
    void actionHappy();
    void actionCurious();
    void actionReset();
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
        uint32_t generation;
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
    bool writeServoAngle(uint8_t channel, int angle);
    bool currentMotionAllowed() const;
    int limitAngle(uint8_t channel, int angle) const;
    size_t servoIndex(uint8_t channel) const;
    const ServoLimit *findServoLimit(uint8_t channel) const;
    esp_err_t enableChannelsAtHome(uint16_t channel_mask, int single_channel);
    bool singleServoRequestAllowed(uint8_t channel, int angle) const; // Under output_mutex_.

    Pca9685Controller pwm_;
    QueueHandle_t command_queue_ = nullptr;
    SemaphoreHandle_t output_mutex_ = nullptr;
    bool control_enabled_ = false; // Protected by output_mutex_.
    int single_channel_ = -1; // -1: whole robot; otherwise only this output is allowed.
    uint32_t generation_ = 0; // Invalidates dequeued/in-progress commands on stop/start.
    uint32_t executing_generation_ = 0; // Only accessed by the motion task.
    int current_angles_[SERVO_LIMIT_COUNT] = {};
    bool ready_ = false;
    bool log_enabled_ = false;
};

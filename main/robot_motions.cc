#include "robot_motions.h"

#include <stdlib.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "robot_motions";
static constexpr size_t MOTION_QUEUE_LENGTH = 8;
static constexpr uint32_t MOTION_TASK_STACK_SIZE = 4096;
static constexpr UBaseType_t MOTION_TASK_PRIORITY = 4;

namespace {
class OutputLock {
public:
    explicit OutputLock(SemaphoreHandle_t mutex) : mutex_(mutex) {
        xSemaphoreTake(mutex_, portMAX_DELAY);
    }
    ~OutputLock() { xSemaphoreGive(mutex_); }
    OutputLock(const OutputLock &) = delete;
    OutputLock &operator=(const OutputLock &) = delete;
private:
    SemaphoreHandle_t mutex_;
};
}

static int clampInt(int value, int min_value, int max_value) {
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

esp_err_t RobotMotions::init() {
    output_mutex_ = xSemaphoreCreateMutex();
    if (output_mutex_ == nullptr) return ESP_ERR_NO_MEM;
    esp_err_t ret = pwm_.init();
    if (ret != ESP_OK) {
        vSemaphoreDelete(output_mutex_);
        output_mutex_ = nullptr;
        return ret;
    }

    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        current_angles_[i] = SERVO_LIMITS[i].home_angle;
    }

    command_queue_ = xQueueCreate(MOTION_QUEUE_LENGTH, sizeof(MotionCommand));
    if (command_queue_ == nullptr) {
        vSemaphoreDelete(output_mutex_);
        output_mutex_ = nullptr;
        ESP_LOGE(TAG, "failed to create motion command queue");
        return ESP_ERR_NO_MEM;
    }

    ready_ = true;
    BaseType_t task_result = xTaskCreate(
        motionTaskEntry,
        "robot_motion_task",
        MOTION_TASK_STACK_SIZE,
        this,
        MOTION_TASK_PRIORITY,
        nullptr);
    if (task_result != pdPASS) {
        ready_ = false;
        vQueueDelete(command_queue_);
        command_queue_ = nullptr;
        vSemaphoreDelete(output_mutex_);
        output_mutex_ = nullptr;
        ESP_LOGE(TAG, "failed to create robot motion task");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "five-servo motion task ready; PWM outputs remain disabled");
    ESP_LOGI(TAG, "舵机通道：左前=%u 右前=%u 左后=%u 右后=%u 尾部=%u（PWM尚未启用）",
             SERVO_FRONT_LEFT, SERVO_FRONT_RIGHT, SERVO_REAR_LEFT, SERVO_REAR_RIGHT, SERVO_TAIL);
    return ESP_OK;
}

esp_err_t RobotMotions::enableOutputsAtHome() {
    return enableChannelsAtHome(SERVO_ALL_CHANNEL_MASK, -1);
}

esp_err_t RobotMotions::enableSingleServoAtHome(uint8_t channel) {
    if (findServoLimit(channel) == nullptr) return ESP_ERR_INVALID_ARG;
    return enableChannelsAtHome(servoChannelMask(channel), channel);
}

esp_err_t RobotMotions::enableChannelsAtHome(uint16_t channel_mask, int single_channel) {
    if (!ready_ || command_queue_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }

    OutputLock lock(output_mutex_);
    // A new session requires explicit stop. Repeated enable must not jump home.
    if (control_enabled_) return ESP_ERR_INVALID_STATE;
    control_enabled_ = false;
    single_channel_ = -1;
    ++generation_;
    xQueueReset(command_queue_);
    esp_err_t ret = pwm_.setOutputsEnabled(false);
    if (ret != ESP_OK) return ret;
    // Stage every home value with its own FULL OFF bit still set.
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        const ServoLimit &limit = SERVO_LIMITS[i];
        if ((channel_mask & servoChannelMask(limit.channel)) == 0) continue;
        const int pulse = SERVO_US_MIN +
                          ((limit.home_angle * (SERVO_US_MAX - SERVO_US_MIN)) / 180);
        ret = pwm_.writeMicroseconds(limit.channel, pulse);
        if (ret != ESP_OK) {
            pwm_.setOutputsEnabled(false);
            return ret;
        }
        current_angles_[i] = limit.home_angle;
    }

    ret = pwm_.setOutputsEnabled(true, channel_mask);
    if (ret == ESP_OK) {
        single_channel_ = single_channel;
        control_enabled_ = true;
        if (single_channel_ < 0) ESP_LOGI(TAG, "servo PWM outputs enabled at home pose");
        else ESP_LOGI(TAG, "单路调试：仅通道%d启用，其余15路PWM关闭", single_channel_);
    }
    return ret;
}

esp_err_t RobotMotions::disableOutputs() {
    if (!ready_ || command_queue_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }

    OutputLock lock(output_mutex_);
    control_enabled_ = false;
    single_channel_ = -1;
    ++generation_;
    xQueueReset(command_queue_);
    esp_err_t ret = pwm_.setOutputsEnabled(false);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "servo PWM outputs disabled (FULL OFF)");
    }
    return ret;
}

bool RobotMotions::isReady() const {
    return ready_;
}

void RobotMotions::setLogEnabled(bool enabled) {
    log_enabled_ = enabled;
}

void RobotMotions::actionShy() {
    enqueueCommand(CommandType::Shy);
}

void RobotMotions::actionHappy() {
    enqueueCommand(CommandType::Happy);
}

void RobotMotions::actionCurious() {
    enqueueCommand(CommandType::Curious);
}

void RobotMotions::actionReset() {
    enqueueCommand(CommandType::Reset);
}

bool RobotMotions::requestServoAngle(uint8_t channel, int angle) {
    const ServoLimit *limit = findServoLimit(channel);
    if (limit == nullptr || angle < limit->min_angle || angle > limit->max_angle) {
        if (log_enabled_) {
            ESP_LOGW(TAG, "unsafe servo request rejected: channel=%u angle=%d", channel, angle);
        }
        return false;
    }
    return enqueueCommand(CommandType::SetServo, channel, angle);
}

void RobotMotions::motionTaskEntry(void *arg) {
    static_cast<RobotMotions *>(arg)->motionTask();
}

void RobotMotions::motionTask() {
    MotionCommand command = {};
    while (true) {
        if (xQueueReceive(command_queue_, &command, portMAX_DELAY) == pdTRUE) {
            executing_generation_ = command.generation;
            executeCommand(command);
        }
    }
}

bool RobotMotions::enqueueCommand(CommandType type, uint8_t channel, int angle) {
    if (!ready_ || command_queue_ == nullptr) {
        if (log_enabled_) {
            ESP_LOGW(TAG, "action skipped: PCA9685 or motion task is not ready");
        }
        return false;
    }

    OutputLock lock(output_mutex_);
    if (!control_enabled_) return false;
    if (single_channel_ >= 0 &&
        (type != CommandType::SetServo || !singleServoRequestAllowed(channel, angle))) return false;
    MotionCommand command = {type, channel, angle, generation_};
    if (xQueueSend(command_queue_, &command, 0) != pdTRUE) {
        ESP_LOGW(TAG, "motion queue full; command dropped");
        return false;
    }
    return true;
}

void RobotMotions::executeCommand(const MotionCommand &command) {
    if (!currentMotionAllowed()) return;
    switch (command.type) {
    case CommandType::Reset:
        executeReset();
        break;
    case CommandType::Shy:
        executeShy();
        break;
    case CommandType::Happy:
        executeHappy();
        break;
    case CommandType::Curious:
        executeCurious();
        break;
    case CommandType::SetServo:
        if (log_enabled_) {
            ESP_LOGI(TAG, "single servo: channel=%u angle=%d", command.channel, command.angle);
        }
        setAngle(command.channel, command.angle);
        break;
    }
}

void RobotMotions::executeShy() {
    if (log_enabled_) {
        ESP_LOGI(TAG, "action: shy");
    }
    const int shy_pose[SERVO_LIMIT_COUNT] = {82, 98, 84, 96, 72};
    moveToPose(shy_pose);
    vTaskDelay(pdMS_TO_TICKS(700));
    executeReset();
}

void RobotMotions::executeHappy() {
    if (log_enabled_) {
        ESP_LOGI(TAG, "action: happy");
    }
    const int pose_a[SERVO_LIMIT_COUNT] = {78, 102, 102, 78, 110};
    const int pose_b[SERVO_LIMIT_COUNT] = {102, 78, 78, 102, 70};
    for (int i = 0; i < 2; ++i) {
        moveToPose(pose_a);
        vTaskDelay(pdMS_TO_TICKS(120));
        moveToPose(pose_b);
        vTaskDelay(pdMS_TO_TICKS(120));
    }
    executeReset();
}

void RobotMotions::executeCurious() {
    if (log_enabled_) {
        ESP_LOGI(TAG, "action: curious");
    }
    const int curious_pose[SERVO_LIMIT_COUNT] = {80, 100, 90, 90, 115};
    moveToPose(curious_pose);
    vTaskDelay(pdMS_TO_TICKS(900));
    executeReset();
}

void RobotMotions::executeReset() {
    if (log_enabled_) {
        ESP_LOGI(TAG, "action: reset");
    }
    int home_pose[SERVO_LIMIT_COUNT] = {};
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        home_pose[i] = SERVO_LIMITS[i].home_angle;
    }
    moveToPose(home_pose);
}

void RobotMotions::moveToPose(const int target_angles[SERVO_LIMIT_COUNT]) {
    int start_angles[SERVO_LIMIT_COUNT] = {};
    int safe_targets[SERVO_LIMIT_COUNT] = {};
    int maximum_delta = 0;

    {
        OutputLock lock(output_mutex_);
        if (!control_enabled_ || executing_generation_ != generation_) return;
        for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
            start_angles[i] = current_angles_[i];
        }
    }
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        safe_targets[i] = limitAngle(SERVO_LIMITS[i].channel, target_angles[i]);
        const int delta = abs(safe_targets[i] - start_angles[i]);
        if (delta > maximum_delta) {
            maximum_delta = delta;
        }
    }

    const int steps = (maximum_delta + SERVO_STEP_DEGREES - 1) / SERVO_STEP_DEGREES;
    if (steps == 0) {
        for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
            if (!writeServoAngle(SERVO_LIMITS[i].channel, safe_targets[i])) return;
        }
        return;
    }

    for (int step_index = 1; step_index <= steps; ++step_index) {
        for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
            const int delta = safe_targets[i] - start_angles[i];
            const int angle = start_angles[i] + (delta * step_index) / steps;
            if (!writeServoAngle(SERVO_LIMITS[i].channel, angle)) return;
        }
        if (step_index < steps) {
            vTaskDelay(pdMS_TO_TICKS(SERVO_STEP_DELAY_MS));
        }
    }
}

void RobotMotions::setAngle(uint8_t channel, int angle) {
    const int target_angle = limitAngle(channel, angle);
    const size_t index = servoIndex(channel);
    int current_angle;
    {
        OutputLock lock(output_mutex_);
        if (!control_enabled_ || executing_generation_ != generation_) return;
        current_angle = current_angles_[index];
    }

    if (current_angle == target_angle) {
        writeServoAngle(channel, target_angle);
        return;
    }

    const int step = current_angle < target_angle ? SERVO_STEP_DEGREES : -SERVO_STEP_DEGREES;
    int position = current_angle;
    while (position != target_angle) {
        position += step;
        if ((step > 0 && position > target_angle) || (step < 0 && position < target_angle)) {
            position = target_angle;
        }
        if (!writeServoAngle(channel, position)) return;
        if (position != target_angle) {
            vTaskDelay(pdMS_TO_TICKS(SERVO_STEP_DELAY_MS));
        }
    }
}

bool RobotMotions::currentMotionAllowed() const {
    OutputLock lock(output_mutex_);
    return control_enabled_ && executing_generation_ == generation_;
}

bool RobotMotions::writeServoAngle(uint8_t channel, int angle) {
    OutputLock lock(output_mutex_);
    if (!control_enabled_ || executing_generation_ != generation_) return false;
    if (!singleServoRequestAllowed(channel, angle)) return false;
    const ServoLimit *limit = findServoLimit(channel);
    if (limit == nullptr) {
        if (log_enabled_) {
            ESP_LOGW(TAG, "unknown servo channel: %u", channel);
        }
        return false;
    }

    const int safe_angle = limitAngle(channel, angle);
    const int pulse = SERVO_US_MIN + ((safe_angle * (SERVO_US_MAX - SERVO_US_MIN)) / 180);
    esp_err_t ret = pwm_.writeMicroseconds(channel, pulse);
    if (ret != ESP_OK) {
        // Stop this session on a bus failure; never continue a partly applied pose.
        control_enabled_ = false;
        single_channel_ = -1;
        ++generation_;
        xQueueReset(command_queue_);
        esp_err_t stop_ret = pwm_.setOutputsEnabled(false);
        ESP_LOGE(TAG, "舵机写入失败：通道%u，%s；停止会话，PWM关闭结果=%s。若异常仍持续请切断舵机电源",
                 channel, esp_err_to_name(ret), esp_err_to_name(stop_ret));
        return false;
    }
    current_angles_[servoIndex(channel)] = safe_angle;
    return true;
}

bool RobotMotions::singleServoRequestAllowed(uint8_t channel, int angle) const {
    if (single_channel_ < 0) return true;
    const ServoLimit *limit = findServoLimit(channel);
    return channel == single_channel_ && limit != nullptr &&
           angle >= limit->home_angle - SERVO_DEBUG_SPAN_DEGREES &&
           angle <= limit->home_angle + SERVO_DEBUG_SPAN_DEGREES;
}

int RobotMotions::limitAngle(uint8_t channel, int angle) const {
    const ServoLimit *limit = findServoLimit(channel);
    if (limit == nullptr) {
        return clampInt(angle, 0, 180);
    }
    return clampInt(angle, limit->min_angle, limit->max_angle);
}

size_t RobotMotions::servoIndex(uint8_t channel) const {
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        if (SERVO_LIMITS[i].channel == channel) {
            return i;
        }
    }
    return 0;
}

const ServoLimit *RobotMotions::findServoLimit(uint8_t channel) const {
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i) {
        if (SERVO_LIMITS[i].channel == channel) {
            return &SERVO_LIMITS[i];
        }
    }
    return nullptr;
}

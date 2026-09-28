// Real production driver/motion sources are linked separately. No ESP, serial,
// network, or real threads are used. The fake models ALL_LED broadcast semantics.
#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <memory>
#include <string>
#include <vector>
#include "../../main/robot_motions.h"
#include "freertos/task.h"

namespace {
std::array<uint8_t, 256> registers{};
int fail_after = -1;
bool bus_down = false;
struct Write { uint8_t reg; std::vector<uint8_t> data; bool ok; uint16_t active; };
std::vector<Write> writes;
std::vector<std::string> logs;
struct Queue { size_t capacity, item_size; std::deque<std::vector<uint8_t>> items; };
std::vector<std::unique_ptr<Queue>> queues;
std::vector<std::unique_ptr<bool>> mutexes;
void (*task_entry)(void *) = nullptr;
void *task_arg = nullptr;
std::function<void()> delay_hook;
struct TaskIdle {};

uint16_t active_mask() {
    uint16_t result = 0;
    for (uint8_t ch = 0; ch < 16; ++ch) {
        if ((registers[0x09 + 4 * ch] & 0x10) == 0) result |= servoChannelMask(ch);
    }
    return result;
}
int pulse_count(uint8_t ch) {
    return registers[0x08 + 4 * ch] | ((registers[0x09 + 4 * ch] & 0x0F) << 8);
}
int angle_count(int angle) {
    const int pulse = SERVO_US_MIN + angle * (SERVO_US_MAX - SERVO_US_MIN) / 180;
    return pulse * 4096 / 20000;
}
void reset_fake() {
    registers.fill(0);
    for (uint8_t ch = 0; ch < 16; ++ch) registers[0x09 + 4 * ch] = 0x10;
    fail_after = -1;
    bus_down = false;
    writes.clear(); logs.clear(); queues.clear(); mutexes.clear();
    delay_hook = {}; task_entry = nullptr; task_arg = nullptr;
}
void run_queued() {
    assert(task_entry);
    try { task_entry(task_arg); } catch (const TaskIdle &) { return; }
    assert(false && "Motion task should reach an empty fake queue");
}
void assert_only_outputs_since(size_t start, uint16_t permitted) {
    for (size_t i = start; i < writes.size(); ++i) {
        assert((writes[i].active & static_cast<uint16_t>(~permitted)) == 0);
    }
}
}

void test_log(const char *, const char *format, ...) {
    char text[1024];
    va_list args; va_start(args, format);
    vsnprintf(text, sizeof(text), format, args); va_end(args);
    logs.emplace_back(text);
}
esp_err_t i2c_param_config(i2c_port_t port, const i2c_config_t *config) {
    assert(port == I2C_NUM_0 && config->sda_io_num == 1 && config->scl_io_num == 2);
    return ESP_OK;
}
esp_err_t i2c_driver_install(i2c_port_t, int, size_t, size_t, int) { return ESP_OK; }
esp_err_t i2c_master_write_to_device(i2c_port_t port, uint8_t address, const uint8_t *data, size_t len, TickType_t) {
    assert(port == I2C_NUM_0 && address == 0x40 && len >= 2);
    bool failed = bus_down;
    if (fail_after == 0) { failed = true; fail_after = -1; }
    else if (fail_after > 0) --fail_after;
    if (!failed) {
        for (size_t i = 1; i < len; ++i) {
            const uint8_t reg = static_cast<uint8_t>(data[0] + i - 1);
            registers[reg] = data[i];
            if (reg >= 0xFA && reg <= 0xFD) {
                for (uint8_t ch = 0; ch < 16; ++ch) registers[0x06 + ch * 4 + reg - 0xFA] = data[i];
            }
        }
    }
    writes.push_back({data[0], std::vector<uint8_t>(data + 1, data + len), !failed, active_mask()});
    return failed ? ESP_FAIL : ESP_OK;
}
esp_err_t i2c_master_write_read_device(i2c_port_t, uint8_t, const uint8_t *reg, size_t, uint8_t *value, size_t, TickType_t) {
    *value = registers[*reg]; return ESP_OK;
}
QueueHandle_t xQueueCreate(UBaseType_t length, UBaseType_t size) {
    queues.push_back(std::make_unique<Queue>(Queue{length, size, {}})); return queues.back().get();
}
BaseType_t xQueueReset(QueueHandle_t handle) { static_cast<Queue *>(handle)->items.clear(); return pdPASS; }
BaseType_t xQueueSend(QueueHandle_t handle, const void *item, TickType_t) {
    auto *queue = static_cast<Queue *>(handle);
    if (queue->items.size() == queue->capacity) return pdFALSE;
    const auto *bytes = static_cast<const uint8_t *>(item);
    queue->items.emplace_back(bytes, bytes + queue->item_size); return pdTRUE;
}
BaseType_t xQueueReceive(QueueHandle_t handle, void *item, TickType_t) {
    auto *queue = static_cast<Queue *>(handle);
    if (queue->items.empty()) throw TaskIdle{};
    memcpy(item, queue->items.front().data(), queue->item_size); queue->items.pop_front(); return pdTRUE;
}
void vQueueDelete(QueueHandle_t) {}
SemaphoreHandle_t xSemaphoreCreateMutex() {
    mutexes.push_back(std::make_unique<bool>(false)); return mutexes.back().get();
}
BaseType_t xSemaphoreTake(SemaphoreHandle_t handle, TickType_t) {
    auto *locked = static_cast<bool *>(handle); assert(!*locked); *locked = true; return pdTRUE;
}
BaseType_t xSemaphoreGive(SemaphoreHandle_t handle) {
    auto *locked = static_cast<bool *>(handle); assert(*locked); *locked = false; return pdTRUE;
}
void vSemaphoreDelete(SemaphoreHandle_t) {}
BaseType_t xTaskCreate(void (*entry)(void *), const char *, uint32_t, void *arg, UBaseType_t, TaskHandle_t *) {
    task_entry = entry; task_arg = arg; return pdPASS;
}
void vTaskDelay(TickType_t) {
    if (delay_hook) { auto callback = std::move(delay_hook); delay_hook = {}; callback(); }
}

int main() {
    static_assert(SERVO_FRONT_LEFT == 15 && SERVO_FRONT_RIGHT == 11 && SERVO_REAR_LEFT == 7 &&
                  SERVO_REAR_RIGHT == 3 && SERVO_TAIL == 0, "Current wiring regression");
    static_assert(SERVO_ALL_CHANNEL_MASK == 0x8889, "Noncontiguous five-channel mask");
    static_assert(servoChannelsValid({0, 1, 2, 3, 4}), "Other mappings are supported");
    static_assert(!servoChannelsValid({15, 11, 7, 3, 15}), "Duplicate rejected");
    static_assert(!servoChannelsValid({16, 11, 7, 3, 0}), "Overflow rejected");
    static_assert(!servoChannelsValid({-1, 11, 7, 3, 0}), "Negative rejected");
    static_assert(servoChannelMask(16) == 0, "Invalid channel cannot shift outside mask");

    reset_fake();
    Pca9685Controller driver;
    assert(driver.init() == ESP_OK && active_mask() == 0);
    for (const auto &limit : SERVO_LIMITS) assert(driver.writeMicroseconds(limit.channel, 1500) == ESP_OK);
    assert(active_mask() == 0);
    assert(driver.setOutputsEnabled(true, SERVO_ALL_CHANNEL_MASK) == ESP_OK);
    assert(active_mask() == SERVO_ALL_CHANNEL_MASK);
    assert(driver.writeMicroseconds(15, 2500) == ESP_OK && pulse_count(15) == 512);
    assert(driver.setOutputsEnabled(false) == ESP_OK && active_mask() == 0);
    assert(driver.writeMicroseconds(15, 2100) == ESP_OK && active_mask() == 0);
    size_t start = writes.size();
    assert(driver.setOutputsEnabled(true, servoChannelMask(SERVO_TAIL)) == ESP_OK);
    assert(driver.writeMicroseconds(15, 2200) == ESP_OK); // Must NOT re-enable a cached leg.
    assert(active_mask() == 1 && pulse_count(15) == 450);
    assert_only_outputs_since(start, 1);
    assert(driver.writeMicroseconds(16, 1500) == ESP_ERR_INVALID_ARG);
    assert(driver.setOutputsEnabled(false) == ESP_OK);
    assert(driver.setOutputsEnabled(true, SERVO_ALL_CHANNEL_MASK) == ESP_OK);
    assert(pulse_count(15) == 450); // FULL OFF/ON must preserve high count bits.

    // Fail each enable transaction; successful best-effort shutdown leaves all off.
    for (int failure = 0; failure <= 16; ++failure) {
        reset_fake(); Pca9685Controller tested;
        assert(tested.init() == ESP_OK);
        for (const auto &limit : SERVO_LIMITS) assert(tested.writeMicroseconds(limit.channel, 1500) == ESP_OK);
        fail_after = failure;
        assert(tested.setOutputsEnabled(true, SERVO_ALL_CHANNEL_MASK) == ESP_FAIL);
        assert(active_mask() == 0);
    }
    reset_fake(); Pca9685Controller unavailable; fail_after = 0;
    assert(unavailable.init() == ESP_FAIL);
    assert(unavailable.setOutputsEnabled(true) == ESP_ERR_INVALID_STATE);

    reset_fake(); RobotMotions robot;
    assert(robot.init() == ESP_OK && active_mask() == 0);
    assert(!robot.requestServoAngle(SERVO_TAIL, 90));
    assert(robot.enableSingleServoAtHome(1) == ESP_ERR_INVALID_ARG);
    assert(robot.enableSingleServoAtHome(SERVO_TAIL) == ESP_OK && active_mask() == 1);
    assert(robot.enableSingleServoAtHome(SERVO_TAIL) == ESP_ERR_INVALID_STATE);
    assert(robot.enableOutputsAtHome() == ESP_ERR_INVALID_STATE);
    assert(!robot.requestServoAngle(SERVO_FRONT_LEFT, 90));
    assert(!robot.requestServoAngle(SERVO_TAIL, 96));
    assert(!robot.requestServoAngle(SERVO_TAIL, 84));
    start = writes.size();
    robot.actionHappy(); robot.actionShy(); robot.actionCurious(); robot.actionReset(); run_queued();
    assert(writes.size() == start); // The motion layer rejects group actions even if a caller bypasses main.
    assert(robot.requestServoAngle(SERVO_TAIL, 95)); run_queued();
    assert(pulse_count(SERVO_TAIL) == angle_count(95));
    assert(robot.requestServoAngle(SERVO_TAIL, 85)); run_queued();
    assert_only_outputs_since(start, 1);

    assert(robot.requestServoAngle(SERVO_TAIL, 90));
    assert(robot.disableOutputs() == ESP_OK);
    start = writes.size(); run_queued(); assert(writes.size() == start && active_mask() == 0);
    assert(robot.enableOutputsAtHome() == ESP_OK && active_mask() == SERVO_ALL_CHANNEL_MASK);
    assert(robot.requestServoAngle(SERVO_FRONT_LEFT, 100)); run_queued();
    assert(pulse_count(15) == angle_count(100));
    assert(robot.requestServoAngle(SERVO_REAR_LEFT, 80)); run_queued();
    assert(pulse_count(7) == angle_count(80));
    start = writes.size(); robot.actionHappy(); run_queued();
    assert_only_outputs_since(start, SERVO_ALL_CHANNEL_MASK);
    for (const auto &limit : SERVO_LIMITS) assert(pulse_count(limit.channel) == angle_count(limit.home_angle));
    assert(robot.disableOutputs() == ESP_OK);

    // Stop/restart during interpolation: an old tail command cannot survive into a leg session.
    assert(robot.enableSingleServoAtHome(SERVO_TAIL) == ESP_OK);
    size_t restart = 0;
    delay_hook = [&] {
        assert(robot.disableOutputs() == ESP_OK); restart = writes.size();
        assert(robot.enableSingleServoAtHome(SERVO_FRONT_LEFT) == ESP_OK);
        assert(robot.requestServoAngle(SERVO_FRONT_LEFT, 92));
    };
    assert(robot.requestServoAngle(SERVO_TAIL, 85)); run_queued();
    assert(restart > 0 && active_mask() == servoChannelMask(SERVO_FRONT_LEFT));
    assert_only_outputs_since(restart, servoChannelMask(SERVO_FRONT_LEFT));
    assert(pulse_count(SERVO_FRONT_LEFT) == angle_count(92));

    // A write failure cancels the session/queue; it is not silently treated as motion success.
    assert(robot.requestServoAngle(SERVO_FRONT_LEFT, 95));
    assert(robot.requestServoAngle(SERVO_FRONT_LEFT, 85));
    fail_after = 0; run_queued();
    assert(active_mask() == 0 && !robot.requestServoAngle(SERVO_FRONT_LEFT, 90));
    assert(robot.enableSingleServoAtHome(SERVO_TAIL) == ESP_OK);
    bus_down = true;
    assert(robot.disableOutputs() == ESP_FAIL);
    assert(!robot.requestServoAngle(SERVO_TAIL, 92));
    // The fake hardware remains enabled when the bus is down: software cannot promise power removal.
    assert(active_mask() == 1);
    bus_down = false; assert(robot.disableOutputs() == ESP_OK && active_mask() == 0);
    puts("servo channel host tests: PASS (15/11/7/3/0 map, masks, tail-only, bounds, broadcast, failures, stop/restart)");
}

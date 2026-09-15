/**
 * @file main.cc
 * @brief ESP32-S3 智能语音助手 - 舵机控制主程序
 *
 * 本程序实现了完整的智能语音助手功能，包括：
 * 1. 语音唤醒检测 - 支持"你好小智"等多种唤醒词
 * 2. 命令词识别 - 支持"帮我开灯"、"帮我关灯"、"拜拜"等语音指令
 * 3. 音频反馈播放 - 通过MAX98357A功放播放确认音频
 * 4. 舵机控制 - 根据语音指令控制舵机旋转
 *
 * 硬件配置：
 * - ESP32-S3-DevKitC-1开发板（需要PSRAM版本）
 * - INMP441数字麦克风（音频输入）
 *   连接方式：VDD->3.3V, GND->GND, SD->GPIO6, WS->GPIO4, SCK->GPIO5
 * - MAX98357A数字功放（音频输出）
 *   连接方式：DIN->GPIO7, BCLK->GPIO15, LRC->GPIO16, VIN->3.3V, GND->GND
 * - PCA9685 五路舵机驱动（GPIO1=SDA, GPIO2=SCL）
 *   舵机使用独立稳压 5V，ESP32、PCA9685 和舵机电源必须共地
 *
 * 音频参数：
 * - 采样率：16kHz
 * - 声道：单声道(Mono)
 * - 位深度：16位
 *
 * 使用的AI模型：
 * - 唤醒词检测：WakeNet9 "你好小智"模型
 * - 命令词识别：MultiNet7中文命令词识别模型
 */

extern "C"
{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wn_iface.h"           // 唤醒词检测接口
#include "esp_wn_models.h"          // 唤醒词模型管理
#include "esp_mn_iface.h"           // 命令词识别接口
#include "esp_mn_models.h"          // 命令词模型管理
#include "esp_mn_speech_commands.h" // 命令词配置
#include "esp_process_sdkconfig.h"  // sdkconfig处理函数
#include "model_path.h"             // 模型路径定义
#include "bsp_board.h"              // 板级支持包，INMP441麦克风驱动
#include "esp_log.h"                // ESP日志系统
#include "esp_timer.h"
#include "mock_voices/welcome.h"    // 欢迎音频数据文件
#include "mock_voices/light_on.h"   // 开灯音频数据文件
#include "mock_voices/light_off.h"  // 关灯音频数据文件
#include "mock_voices/byebye.h"     // 再见音频数据文件
#include "driver/gpio.h"            // GPIO驱动
#include "driver/ledc.h"            // LEDC PWM驱动，用于舵机控制
}

#include "ai_client.h"
#include "audio_reply_player.h"
#include "audio_recorder.h"
#include "network_config.h"
#include "servo_controller.h" // 舵机控制器类
#include "robot_motions.h"
#include "touch_inputs.h"
#include "wifi_manager.h"

static const char *TAG = "舵机控制"; // 日志标签
static const char *FIRMWARE_NAME = "PRP voice-servo AI bridge";
static const char *FIRMWARE_VERSION = "2026-09-15-latency-v1";

// 系统状态定义
typedef enum
{
    STATE_WAITING_WAKEUP = 0,  // 等待唤醒词
    STATE_WAITING_COMMAND = 1, // 等待命令词
} system_state_t;

// 命令词ID定义（对应commands_cn.txt中的ID）
#define COMMAND_TURN_OFF_LIGHT 308 // "帮我关灯"
#define COMMAND_TURN_ON_LIGHT 309  // "帮我开灯"
#define COMMAND_BYE_BYE 314        // "拜拜"

// 命令词配置结构体
typedef struct
{
    int command_id;
    const char *pinyin;
    const char *description;
} command_config_t;

// 自定义命令词列表
static const command_config_t custom_commands[] = {
    {COMMAND_TURN_ON_LIGHT, "bang wo kai deng", "帮我开灯"},
    {COMMAND_TURN_OFF_LIGHT, "bang wo guan deng", "帮我关灯"},
    {COMMAND_BYE_BYE, "bai bai", "拜拜"},
};

#define CUSTOM_COMMANDS_COUNT (sizeof(custom_commands) / sizeof(custom_commands[0]))

// 全局变量
static system_state_t current_state = STATE_WAITING_WAKEUP;
static esp_mn_iface_t *multinet = NULL;
static model_iface_data_t *mn_model_data = NULL;
static TickType_t command_timeout_start = 0;
static const TickType_t COMMAND_TIMEOUT_MS = 5000; // 5秒超时

// 舵机控制器实例
static ServoController servo_controller;
static RobotMotions robot_motions;
static TouchInputs touch_inputs;
static bool machine_log_enabled = false;
static bool machine_control_enabled = false;
static bool ai_bridge_ready = false;

typedef enum
{
    AI_INTERACTION_OK = 0,
    AI_INTERACTION_SKIPPED,
    AI_INTERACTION_NO_SPEECH,
    AI_INTERACTION_FAILED,
} ai_interaction_result_t;

static void trim_line(char *text)
{
    size_t len = strlen(text);
    while (len > 0 && (text[len - 1] == '\n' || text[len - 1] == '\r' || text[len - 1] == ' '))
    {
        text[len - 1] = '\0';
        len--;
    }
}

static const ServoLimit *get_servo_limit(uint8_t channel)
{
    for (size_t i = 0; i < SERVO_LIMIT_COUNT; ++i)
    {
        if (SERVO_LIMITS[i].channel == channel)
        {
            return &SERVO_LIMITS[i];
        }
    }
    return nullptr;
}

static bool servo_channel_from_name(const char *name, uint8_t *channel)
{
    if (strcmp(name, "fl") == 0)
    {
        *channel = SERVO_FRONT_LEFT;
    }
    else if (strcmp(name, "fr") == 0)
    {
        *channel = SERVO_FRONT_RIGHT;
    }
    else if (strcmp(name, "rl") == 0)
    {
        *channel = SERVO_REAR_LEFT;
    }
    else if (strcmp(name, "rr") == 0)
    {
        *channel = SERVO_REAR_RIGHT;
    }
    else if (strcmp(name, "tail") == 0)
    {
        *channel = SERVO_TAIL;
    }
    else
    {
        return false;
    }
    return true;
}

static void handle_serial_servo_command(const char *line)
{
    char name[8] = {};
    int angle = 0;
    char extra = '\0';
    if (sscanf(line, "servo %7s %d %c", name, &angle, &extra) != 2)
    {
        ESP_LOGW(TAG, "Usage: servo <fl|fr|rl|rr|tail> <angle>");
        return;
    }

    uint8_t channel = 0;
    if (!servo_channel_from_name(name, &channel))
    {
        ESP_LOGW(TAG, "Unknown servo '%s'; use fl, fr, rl, rr, or tail", name);
        return;
    }

    const ServoLimit *limit = get_servo_limit(channel);
    if (limit == nullptr || angle < limit->min_angle || angle > limit->max_angle)
    {
        ESP_LOGW(TAG, "Angle rejected for %s; safe range is %d-%d degrees",
                 name,
                 limit != nullptr ? limit->min_angle : 0,
                 limit != nullptr ? limit->max_angle : 0);
        return;
    }

    if (!robot_motions.requestServoAngle(channel, angle))
    {
        ESP_LOGW(TAG, "Servo command not queued; check PCA9685 status and motion queue");
        return;
    }
    ESP_LOGI(TAG, "Servo command queued: %s channel=%u angle=%d", name, channel, angle);
}

static void serial_command_task(void *arg)
{
    (void)arg;
    char line[96];

    ESP_LOGI(TAG, "Serial commands ready: machine control/log, motion <name>, servo <name> <angle>, AI bridge status/retry");

    while (1)
    {
        if (fgets(line, sizeof(line), stdin) == NULL)
        {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        trim_line(line);

        if (strcmp(line, "start log machine") == 0)
        {
            machine_log_enabled = true;
            robot_motions.setLogEnabled(true);
            ESP_LOGI(TAG, "Machine module logs enabled");
        }
        else if (strcmp(line, "end log machine") == 0)
        {
            machine_log_enabled = false;
            robot_motions.setLogEnabled(false);
            ESP_LOGI(TAG, "Machine module logs disabled");
        }
        else if (strcmp(line, "start machine control") == 0)
        {
            machine_control_enabled = true;
            ESP_LOGI(TAG, "Machine control enabled (touch inputs compiled %s)",
                     TOUCH_INPUTS_ENABLED ? "on" : "off");
        }
        else if (strcmp(line, "end machine control") == 0)
        {
            machine_control_enabled = false;
            robot_motions.cancelPendingAndReset();
            ESP_LOGI(TAG, "Machine control disabled");
        }
        else if (strcmp(line, "motion reset") == 0 || strcmp(line, "motion shy") == 0 ||
                 strcmp(line, "motion happy") == 0 || strcmp(line, "motion curious") == 0)
        {
            if (!machine_control_enabled)
            {
                ESP_LOGW(TAG, "Machine control is disabled; run 'start machine control' first");
            }
            else if (strcmp(line, "motion reset") == 0)
            {
                robot_motions.actionReset();
            }
            else if (strcmp(line, "motion shy") == 0)
            {
                robot_motions.actionShy();
            }
            else if (strcmp(line, "motion happy") == 0)
            {
                robot_motions.actionHappy();
            }
            else
            {
                robot_motions.actionCurious();
            }
        }
        else if (strncmp(line, "servo ", 6) == 0)
        {
            if (!machine_control_enabled)
            {
                ESP_LOGW(TAG, "Machine control is disabled; run 'start machine control' first");
            }
            else
            {
                handle_serial_servo_command(line);
            }
        }
        else if (strcmp(line, "status ai bridge") == 0)
        {
            ESP_LOGI(TAG, "Firmware: %s (%s)", FIRMWARE_NAME, FIRMWARE_VERSION);
            ESP_LOGI(TAG, "AI bridge enabled: %d", AI_BRIDGE_ENABLED);
            ESP_LOGI(TAG, "Wi-Fi status: %s", wifi_manager_status_text());
            ESP_LOGI(TAG, "AI bridge ready: %d", ai_bridge_ready);
            ESP_LOGI(TAG, "AI server URL: %s", AI_SERVER_URL);
        }
        else if (strcmp(line, "retry wifi") == 0)
        {
            esp_err_t wifi_ret = wifi_manager_start();
            ai_bridge_ready = (wifi_ret == ESP_OK);
            ESP_LOGI(TAG, "Wi-Fi retry result: %s, AI bridge ready: %d",
                     esp_err_to_name(wifi_ret), ai_bridge_ready);
        }
    }
}

static void handle_touch_event()
{
    if (!TOUCH_INPUTS_ENABLED || !machine_control_enabled)
    {
        return;
    }

    switch (touch_inputs.poll())
    {
    case TouchEvent::Touch1:
        if (machine_log_enabled)
        {
            ESP_LOGI(TAG, "Touch 1 detected -> shy action");
        }
        robot_motions.actionShy();
        break;
    case TouchEvent::Touch2:
        if (machine_log_enabled)
        {
            ESP_LOGI(TAG, "Touch 2 detected -> happy action");
        }
        robot_motions.actionHappy();
        break;
    case TouchEvent::Touch3:
        if (machine_log_enabled)
        {
            ESP_LOGI(TAG, "Touch 3 detected -> curious action");
        }
        robot_motions.actionCurious();
        break;
    case TouchEvent::None:
    default:
        break;
    }
}

static void dispatch_ai_motion(const char *motion)
{
    if (motion == NULL || motion[0] == '\0' || strcmp(motion, "none") == 0)
    {
        return;
    }

    if (!machine_control_enabled)
    {
        if (machine_log_enabled)
        {
            ESP_LOGI(TAG, "AI motion skipped because machine control is disabled: %s", motion);
        }
        return;
    }

    if (strcmp(motion, "happy") == 0)
    {
        robot_motions.actionHappy();
    }
    else if (strcmp(motion, "shy") == 0)
    {
        robot_motions.actionShy();
    }
    else if (strcmp(motion, "comfort") == 0 || strcmp(motion, "curious") == 0)
    {
        robot_motions.actionCurious();
    }
    else
    {
        ESP_LOGW(TAG, "Unknown AI motion intent: %s", motion);
    }
}

static bool ensure_ai_bridge_ready()
{
    if (!AI_BRIDGE_ENABLED)
    {
        ESP_LOGW(TAG, "AI bridge skipped: AI_BRIDGE_ENABLED=0");
        return false;
    }

    if (wifi_manager_is_connected())
    {
        if (!ai_bridge_ready)
        {
            ai_bridge_ready = true;
            ESP_LOGI(TAG, "AI bridge recovered: Wi-Fi is connected, server=%s", AI_SERVER_URL);
        }
        return true;
    }

    ai_bridge_ready = false;
    ESP_LOGW(TAG, "AI bridge skipped: Wi-Fi status=%s, server=%s. Use 'retry wifi' after network is ready.",
             wifi_manager_status_text(), AI_SERVER_URL);
    return false;
}

static ai_interaction_result_t run_ai_bridge_interaction(int audio_chunksize, uint32_t start_timeout_ms)
{
    if (!ensure_ai_bridge_ready())
    {
        return AI_INTERACTION_SKIPPED;
    }

    audio_recording_t recording = {};
    voice_trace_t trace;
    voice_trace_init(&trace);
    ESP_LOGI(TAG, "AI bridge recording started: endpoint=%d, start_timeout=%u ms, fixed_duration=%d ms",
             AI_RECORD_ENDPOINT_ENABLED, (unsigned)start_timeout_ms, AI_RECORD_DURATION_MS);
#if AI_RECORD_ENDPOINT_ENABLED
    esp_err_t ret = audio_recorder_record_pcm_endpoint(&recording, audio_chunksize, start_timeout_ms);
#else
    esp_err_t ret = audio_recorder_record_pcm(&recording, AI_RECORD_DURATION_MS, audio_chunksize);
#endif
    voice_trace_mark(&trace, "recording_end", &trace.recording_end_us);
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "AI bridge recording failed: %s", esp_err_to_name(ret));
        voice_trace_finish(&trace, ret == ESP_ERR_TIMEOUT ? "no_speech" : "recording_failed");
        return ret == ESP_ERR_TIMEOUT ? AI_INTERACTION_NO_SPEECH : AI_INTERACTION_FAILED;
    }

    ESP_LOGI(TAG, "AI bridge recording finished: %u bytes captured, uploading to server",
             (unsigned)recording.byte_len);
    ai_response_t response = {};
    int64_t request_start_us = esp_timer_get_time();
    ret = ai_client_send_pcm(recording.samples, recording.byte_len, recording.sample_rate, &response, &trace);
    int request_ms = (int)((esp_timer_get_time() - request_start_us) / 1000);
    audio_recorder_free(&recording);

    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "AI bridge request failed: %s", esp_err_to_name(ret));
        voice_trace_finish(&trace, "request_failed");
        return AI_INTERACTION_FAILED;
    }

    ESP_LOGI(TAG,
             "AI latency: request_roundtrip=%d ms, server_total=%d ms (asr=%d, reply=%d, tts=%d)",
             request_ms,
             response.total_pipeline_ms,
             response.asr_ms,
             response.dialogue_ms,
             response.tts_ms);
    ESP_LOGI(TAG, "AI bridge response text: %s", response.reply_text);
    ESP_LOGI(TAG, "VOICE_SERVER id=%s body_receive_ms=%d prepare_audio_ms=%d asr_ms=%d dialogue_ms=%d "
             "tts_ms=%d total_pipeline_ms=%d total_request_ms=%d",
             trace.request_id, response.body_receive_ms, response.prepare_audio_ms, response.asr_ms,
             response.dialogue_ms, response.tts_ms, response.total_pipeline_ms, response.total_request_ms);
    dispatch_ai_motion(response.motion);
    const char *trace_result = "no_audio";
    if (response.audio_url[0] != '\0')
    {
        esp_err_t play_ret = audio_reply_play_from_url(response.audio_url, &trace);
        trace_result = play_ret == ESP_OK ? "ok" : "audio_failed";
        if (play_ret != ESP_OK)
        {
            ESP_LOGW(TAG, "Reply audio playback failed: %s", esp_err_to_name(play_ret));
        }
    }
    voice_trace_finish(&trace, trace_result);
    return AI_INTERACTION_OK;
}

static ai_interaction_result_t run_ai_bridge_conversation(int audio_chunksize)
{
    ai_interaction_result_t result = run_ai_bridge_interaction(audio_chunksize, AI_RECORD_START_TIMEOUT_MS);
    if (result != AI_INTERACTION_OK)
    {
        return result;
    }

#if AI_CHAT_CONTINUE_ENABLED
    for (int turn = 0; turn < AI_CHAT_MAX_FOLLOWUP_TURNS; turn++)
    {
        ESP_LOGI(TAG, "AI bridge follow-up listening: turn=%d/%d, timeout=%d ms",
                 turn + 1, AI_CHAT_MAX_FOLLOWUP_TURNS, AI_CHAT_FOLLOWUP_TIMEOUT_MS);
        result = run_ai_bridge_interaction(audio_chunksize, AI_CHAT_FOLLOWUP_TIMEOUT_MS);
        if (result == AI_INTERACTION_OK)
        {
            continue;
        }
        if (result == AI_INTERACTION_NO_SPEECH)
        {
            ESP_LOGI(TAG, "AI bridge conversation ended: no follow-up speech");
            return AI_INTERACTION_OK;
        }
        return result;
    }
    ESP_LOGI(TAG, "AI bridge conversation ended: max follow-up turns reached");
#endif

    return AI_INTERACTION_OK;
}

/**
 * @brief 配置自定义命令词
 *
 * 该函数会清除现有命令词，然后添加自定义命令词列表中的所有命令
 *
 * @param multinet 命令词识别接口指针
 * @param mn_model_data 命令词模型数据指针
 * @return esp_err_t
 *         - ESP_OK: 配置成功
 *         - ESP_FAIL: 配置失败
 */
static esp_err_t configure_custom_commands(esp_mn_iface_t *multinet, model_iface_data_t *mn_model_data)
{
    ESP_LOGI(TAG, "开始配置自定义命令词...");

    // 首先尝试从sdkconfig加载默认命令词配置
    esp_mn_commands_update_from_sdkconfig(multinet, mn_model_data);

    // 清除现有命令词，重新开始
    esp_mn_commands_clear();

    // 分配命令词管理结构
    esp_err_t ret = esp_mn_commands_alloc(multinet, mn_model_data);
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "命令词管理结构分配失败: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }

    // 添加自定义命令词
    int success_count = 0;
    int fail_count = 0;

    for (int i = 0; i < CUSTOM_COMMANDS_COUNT; i++)
    {
        const command_config_t *cmd = &custom_commands[i];

        ESP_LOGI(TAG, "添加命令词 [%d]: %s (%s)",
                 cmd->command_id, cmd->description, cmd->pinyin);

        // 添加命令词
        esp_err_t ret_cmd = esp_mn_commands_add(cmd->command_id, cmd->pinyin);
        if (ret_cmd == ESP_OK)
        {
            success_count++;
            ESP_LOGI(TAG, "✓ 命令词 [%d] 添加成功", cmd->command_id);
        }
        else
        {
            fail_count++;
            ESP_LOGE(TAG, "✗ 命令词 [%d] 添加失败: %s",
                     cmd->command_id, esp_err_to_name(ret_cmd));
        }
    }

    // 更新命令词到模型
    ESP_LOGI(TAG, "更新命令词到模型...");
    esp_mn_error_t *error_phrases = esp_mn_commands_update();
    if (error_phrases != NULL && error_phrases->num > 0)
    {
        ESP_LOGW(TAG, "有 %d 个命令词更新失败:", error_phrases->num);
        for (int i = 0; i < error_phrases->num; i++)
        {
            ESP_LOGW(TAG, "  失败命令 %d: %s",
                     error_phrases->phrases[i]->command_id,
                     error_phrases->phrases[i]->string);
        }
    }

    // 打印配置结果
    ESP_LOGI(TAG, "命令词配置完成: 成功 %d 个, 失败 %d 个", success_count, fail_count);

    // 打印激活的命令词
    ESP_LOGI(TAG, "当前激活的命令词列表:");
    multinet->print_active_speech_commands(mn_model_data);

    // 打印支持的命令列表
    ESP_LOGI(TAG, "支持的语音命令:");
    for (int i = 0; i < CUSTOM_COMMANDS_COUNT; i++)
    {
        const command_config_t *cmd = &custom_commands[i];
        ESP_LOGI(TAG, "  ID=%d: '%s'", cmd->command_id, cmd->description);
    }

    return (fail_count == 0) ? ESP_OK : ESP_FAIL;
}

/**
 * @brief 获取命令词的中文描述
 *
 * @param command_id 命令ID
 * @return const char* 命令的中文描述，如果未找到返回"未知命令"
 */
static const char *get_command_description(int command_id)
{
    for (int i = 0; i < CUSTOM_COMMANDS_COUNT; i++)
    {
        if (custom_commands[i].command_id == command_id)
        {
            return custom_commands[i].description;
        }
    }
    return "未知命令";
}

/**
 * @brief 执行退出逻辑
 *
 * 播放再见音频并返回等待唤醒状态
 */
static void execute_exit_logic(void)
{
    // 播放再见音频
    ESP_LOGI(TAG, "播放再见音频...");
    esp_err_t audio_ret = bsp_play_audio(byebye, byebye_len);
    if (audio_ret == ESP_OK)
    {
        ESP_LOGI(TAG, "✓ 再见音频播放成功");
    }
    else
    {
        ESP_LOGE(TAG, "再见音频播放失败: %s", esp_err_to_name(audio_ret));
    }

    current_state = STATE_WAITING_WAKEUP;
    ESP_LOGI(TAG, "返回等待唤醒状态，请说出唤醒词 '你好小智'");
}

/**
 * @brief 应用程序主入口函数
 *
 * 初始化INMP441麦克风硬件，加载唤醒词检测模型，
 * 然后进入主循环进行实时音频采集和唤醒词检测。
 */
extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Booting %s (%s)", FIRMWARE_NAME, FIRMWARE_VERSION);

    // ========== 第一步：初始化舵机 ==========
    esp_err_t motion_ret = robot_motions.init();
    if (motion_ret != ESP_OK)
    {
        ESP_LOGW(TAG, "Robot motion init failed, voice-only test mode continues: %s", esp_err_to_name(motion_ret));
    }

    if (TOUCH_INPUTS_ENABLED)
    {
        esp_err_t touch_ret = touch_inputs.init();
        if (touch_ret != ESP_OK)
        {
            ESP_LOGW(TAG, "Touch input init failed, voice-only test mode continues: %s", esp_err_to_name(touch_ret));
        }
    }
    else
    {
        ESP_LOGI(TAG, "Touch inputs disabled for servo bench testing");
    }

    xTaskCreate(serial_command_task, "serial_command_task", 4096, NULL, 5, NULL);

    if (AI_BRIDGE_ENABLED)
    {
        esp_err_t wifi_ret = wifi_manager_start();
        ai_bridge_ready = (wifi_ret == ESP_OK);
        if (ai_bridge_ready)
        {
            ESP_LOGI(TAG, "AI bridge networking is ready");
        }
        else
        {
            ESP_LOGW(TAG, "AI bridge networking is not ready, local command mode remains available");
        }
    }

    // ========== 第二步：初始化INMP441麦克风硬件 ==========
    ESP_LOGI(TAG, "正在初始化INMP441数字麦克风...");
    ESP_LOGI(TAG, "音频参数: 采样率16kHz, 单声道, 16位深度");

    esp_err_t ret = bsp_board_init(16000, 1, 16); // 16kHz, 单声道, 16位
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "INMP441麦克风初始化失败: %s", esp_err_to_name(ret));
        ESP_LOGE(TAG, "请检查硬件连接: VDD->3.3V, GND->GND, SD->GPIO6, WS->GPIO4, SCK->GPIO5");
        return;
    }
    ESP_LOGI(TAG, "✓ INMP441麦克风初始化成功");

    // ========== 第三步：初始化音频播放功能 ==========
    ESP_LOGI(TAG, "正在初始化音频播放功能...");
    ESP_LOGI(TAG, "音频播放参数: 采样率16kHz, 单声道, 16位深度");

    ret = bsp_audio_init(16000, 1, 16); // 16kHz, 单声道, 16位
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "音频播放初始化失败: %s", esp_err_to_name(ret));
        ESP_LOGE(TAG, "请检查MAX98357A硬件连接: DIN->GPIO7, BCLK->GPIO15, LRC->GPIO16");
        return;
    }
    ESP_LOGI(TAG, "✓ 音频播放初始化成功");

    // ========== 第四步：初始化语音识别模型 ==========
    ESP_LOGI(TAG, "正在初始化唤醒词检测模型...");

    // 检查内存状态
    size_t free_heap = heap_caps_get_free_size(MALLOC_CAP_8BIT);
    size_t free_internal = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    size_t free_spiram = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);

    ESP_LOGI(TAG, "内存状态检查:");
    ESP_LOGI(TAG, "  - 总可用内存: %zu KB", free_heap / 1024);
    ESP_LOGI(TAG, "  - 内部RAM: %zu KB", free_internal / 1024);
    ESP_LOGI(TAG, "  - PSRAM: %zu KB", free_spiram / 1024);

    if (free_heap < 100 * 1024)
    {
        ESP_LOGE(TAG, "可用内存不足，需要至少100KB");
        return;
    }

    // 从模型目录加载所有可用的语音识别模型
    ESP_LOGI(TAG, "开始加载模型文件...");

    // 临时添加错误处理和重试机制
    srmodel_list_t *models = NULL;
    int retry_count = 0;
    const int max_retries = 3;

    while (models == NULL && retry_count < max_retries)
    {
        ESP_LOGI(TAG, "尝试加载模型 (第%d次)...", retry_count + 1);

        // 在每次重试前等待一下
        if (retry_count > 0)
        {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }

        models = esp_srmodel_init("model");

        if (models == NULL)
        {
            ESP_LOGW(TAG, "模型加载失败，准备重试...");
            retry_count++;
        }
    }
    if (models == NULL)
    {
        ESP_LOGE(TAG, "语音识别模型初始化失败");
        ESP_LOGE(TAG, "请检查模型文件是否正确烧录到Flash分区");
        return;
    }

    // 自动选择sdkconfig中配置的唤醒词模型（如果配置了多个模型则选择第一个）
    char *model_name = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
    if (model_name == NULL)
    {
        ESP_LOGE(TAG, "未找到任何唤醒词模型！");
        ESP_LOGE(TAG, "请确保已正确配置并烧录唤醒词模型文件");
        ESP_LOGE(TAG, "可通过 'idf.py menuconfig' 配置唤醒词模型");
        return;
    }

    ESP_LOGI(TAG, "✓ 选择唤醒词模型: %s", model_name);

    // 获取唤醒词检测接口
    esp_wn_iface_t *wakenet = (esp_wn_iface_t *)esp_wn_handle_from_name(model_name);
    if (wakenet == NULL)
    {
        ESP_LOGE(TAG, "获取唤醒词接口失败，模型: %s", model_name);
        return;
    }

    // 创建唤醒词模型数据实例
    // DET_MODE_90: 检测模式，90%置信度阈值，平衡准确率和误触发率
    model_iface_data_t *model_data = wakenet->create(model_name, DET_MODE_90);
    if (model_data == NULL)
    {
        ESP_LOGE(TAG, "创建唤醒词模型数据失败");
        return;
    }

    // ========== 第五步：初始化命令词识别模型 ==========
    ESP_LOGI(TAG, "正在初始化命令词识别模型...");

    // 获取中文命令词识别模型（MultiNet7）
    char *mn_name = esp_srmodel_filter(models, ESP_MN_PREFIX, ESP_MN_CHINESE);
    if (mn_name == NULL)
    {
        ESP_LOGE(TAG, "未找到中文命令词识别模型！");
        ESP_LOGE(TAG, "请确保已正确配置并烧录MultiNet7中文模型");
        return;
    }

    ESP_LOGI(TAG, "✓ 选择命令词模型: %s", mn_name);

    // 获取命令词识别接口
    multinet = esp_mn_handle_from_name(mn_name);
    if (multinet == NULL)
    {
        ESP_LOGE(TAG, "获取命令词识别接口失败，模型: %s", mn_name);
        return;
    }

    // 创建命令词模型数据实例
    mn_model_data = multinet->create(mn_name, 6000);
    if (mn_model_data == NULL)
    {
        ESP_LOGE(TAG, "创建命令词模型数据失败");
        return;
    }

    // 配置自定义命令词
    ESP_LOGI(TAG, "正在配置命令词...");
    esp_err_t cmd_config_ret = configure_custom_commands(multinet, mn_model_data);
    if (cmd_config_ret != ESP_OK)
    {
        ESP_LOGE(TAG, "命令词配置失败");
        return;
    }
    ESP_LOGI(TAG, "✓ 命令词配置完成");

    // ========== 第六步：准备音频缓冲区 ==========
    // 获取模型要求的音频数据块大小（样本数 × 每样本字节数）
    int audio_chunksize = wakenet->get_samp_chunksize(model_data) * sizeof(int16_t);

    // 分配音频数据缓冲区内存
    int16_t *buffer = (int16_t *)malloc(audio_chunksize);
    if (buffer == NULL)
    {
        ESP_LOGE(TAG, "音频缓冲区内存分配失败，需要 %d 字节", audio_chunksize);
        ESP_LOGE(TAG, "请检查系统可用内存");
        return;
    }

    // 显示系统配置信息
    ESP_LOGI(TAG, "✓ 智能语音助手系统配置完成:");
    ESP_LOGI(TAG, "  - 唤醒词模型: %s", model_name);
    ESP_LOGI(TAG, "  - 命令词模型: %s", mn_name);
    ESP_LOGI(TAG, "  - 音频块大小: %d 字节", audio_chunksize);
    ESP_LOGI(TAG, "  - 检测置信度: 90%%");
    ESP_LOGI(TAG, "正在启动智能语音助手...");
    ESP_LOGI(TAG, "请对着麦克风说出唤醒词 '你好小智'");

    // ========== 第七步：主循环 - 实时音频采集与语音识别 ==========
    ESP_LOGI(TAG, "系统启动完成，等待唤醒词 '你好小智'...");

    while (1)
    {
        // 从INMP441麦克风获取一帧音频数据
        // false参数表示获取处理后的音频数据（非原始通道数据）
        esp_err_t ret = bsp_get_feed_data(false, buffer, audio_chunksize);
        if (ret != ESP_OK)
        {
            ESP_LOGE(TAG, "麦克风音频数据获取失败: %s", esp_err_to_name(ret));
            ESP_LOGE(TAG, "请检查INMP441硬件连接");
            vTaskDelay(pdMS_TO_TICKS(10)); // 等待10ms后重试
            continue;
        }

        handle_touch_event();

        if (current_state == STATE_WAITING_WAKEUP)
        {
            // 第一阶段：唤醒词检测
            wakenet_state_t wn_state = wakenet->detect(model_data, buffer);

            if (wn_state == WAKENET_DETECTED)
            {
                ESP_LOGI(TAG, "🎉 检测到唤醒词 '你好小智'！");
                printf("=== 唤醒词检测成功！模型: %s ===\n", model_name);

                // 播放欢迎音频
                ESP_LOGI(TAG, "播放欢迎音频...");
                esp_err_t audio_ret = bsp_play_audio(welcome, welcome_len);
                if (audio_ret != ESP_OK)
                {
                    ESP_LOGE(TAG, "音频播放失败: %s", esp_err_to_name(audio_ret));
                }
                else
                {
                    ESP_LOGI(TAG, "✓ 欢迎音频播放成功");
                }

                ai_interaction_result_t ai_result = run_ai_bridge_conversation(audio_chunksize);
                if (ai_result == AI_INTERACTION_OK)
                {
                    current_state = STATE_WAITING_WAKEUP;
                    ESP_LOGI(TAG, "AI bridge interaction finished, returning to wake word mode");
                    continue;
                }
                if (ai_result == AI_INTERACTION_NO_SPEECH)
                {
                    current_state = STATE_WAITING_WAKEUP;
                    ESP_LOGI(TAG, "AI bridge interaction ended without speech, returning to wake word mode");
                    continue;
                }
                ESP_LOGW(TAG, "AI bridge interaction skipped or failed, entering local command mode");

                // 切换到命令词识别状态
                current_state = STATE_WAITING_COMMAND;
                command_timeout_start = xTaskGetTickCount();
                multinet->clean(mn_model_data); // 清理命令词识别缓冲区
                ESP_LOGI(TAG, "进入命令词识别模式，请说出指令...");
                ESP_LOGI(TAG, "支持的指令: '帮我开灯'（顺时针45°）、'帮我关灯'（逆时针45°）或 '拜拜'");
            }
        }
        else if (current_state == STATE_WAITING_COMMAND)
        {
            // 第二阶段：命令词识别
            esp_mn_state_t mn_state = multinet->detect(mn_model_data, buffer);

            if (mn_state == ESP_MN_STATE_DETECTED)
            {
                // 获取识别结果
                esp_mn_results_t *mn_result = multinet->get_results(mn_model_data);
                if (mn_result->num > 0)
                {
                    int command_id = mn_result->command_id[0];
                    float prob = mn_result->prob[0];

                    const char *cmd_desc = get_command_description(command_id);
                    ESP_LOGI(TAG, "🎯 检测到命令词: ID=%d, 置信度=%.2f, 内容=%s, 命令='%s'",
                             command_id, prob, mn_result->string, cmd_desc);

                    // 处理具体命令
                    if (command_id == COMMAND_TURN_ON_LIGHT)
                    {
                        ESP_LOGI(TAG, "🔄 执行开灯命令 - 舵机顺时针旋转45度");
                        if (machine_control_enabled)
                        {
                            robot_motions.actionHappy();
                        }

                        // 播放开灯确认音频
                        esp_err_t audio_ret = bsp_play_audio(light_on, light_on_len);
                        if (audio_ret == ESP_OK)
                        {
                            ESP_LOGI(TAG, "✓ 舵机旋转确认音频播放成功");
                        }
                    }
                    else if (command_id == COMMAND_TURN_OFF_LIGHT)
                    {
                        ESP_LOGI(TAG, "🔄 执行关灯命令 - 舵机逆时针旋转45度");
                        if (machine_control_enabled)
                        {
                            robot_motions.actionShy();
                        }

                        // 播放关灯确认音频
                        esp_err_t audio_ret = bsp_play_audio(light_off, light_off_len);
                        if (audio_ret == ESP_OK)
                        {
                            ESP_LOGI(TAG, "✓ 舵机旋转确认音频播放成功");
                        }
                    }
                    else if (command_id == COMMAND_BYE_BYE)
                    {
                        ESP_LOGI(TAG, "👋 检测到拜拜命令，立即退出");
                        execute_exit_logic();
                        continue; // 跳过后续的超时重置逻辑，直接进入下一次循环
                    }
                    else
                    {
                        ESP_LOGW(TAG, "⚠️  未知命令ID: %d", command_id);
                    }
                }

                // 命令处理完成，重新开始5秒倒计时，继续等待下一个命令
                command_timeout_start = xTaskGetTickCount();
                multinet->clean(mn_model_data); // 清理命令词识别缓冲区
                ESP_LOGI(TAG, "舵机控制命令执行完成，重新开始5秒倒计时");
                ESP_LOGI(TAG, "可以继续说出指令: '帮我开灯'（顺时针45°）、'帮我关灯'（逆时针45°）或 '拜拜'");
            }
            else if (mn_state == ESP_MN_STATE_TIMEOUT)
            {
                ESP_LOGW(TAG, "⏰ 命令词识别超时");
                execute_exit_logic();
            }
            else
            {
                // 检查手动超时
                TickType_t current_time = xTaskGetTickCount();
                if ((current_time - command_timeout_start) > pdMS_TO_TICKS(COMMAND_TIMEOUT_MS))
                {
                    ESP_LOGW(TAG, "⏰ 命令词等待超时 (%lu秒)", (unsigned long)(COMMAND_TIMEOUT_MS / 1000));
                    execute_exit_logic();
                }
            }
        }

        // 短暂延时，避免CPU占用过高，同时保证实时性
        vTaskDelay(pdMS_TO_TICKS(1));
    }

    // ========== 资源清理 ==========
    // 注意：由于主循环是无限循环，以下代码正常情况下不会执行
    // 仅在程序异常退出时进行资源清理
    ESP_LOGI(TAG, "正在清理系统资源...");

    // 销毁唤醒词模型数据
    if (model_data != NULL)
    {
        wakenet->destroy(model_data);
    }

    // 释放音频缓冲区内存
    if (buffer != NULL)
    {
        free(buffer);
    }

    // 删除当前任务
    vTaskDelete(NULL);
}

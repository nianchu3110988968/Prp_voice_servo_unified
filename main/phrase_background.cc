#include "phrase_background.h"
#include "audio_reply_player.h"
#include <new>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "语音后台";
static portMUX_TYPE slots_lock = portMUX_INITIALIZER_UNLOCKED;
static unsigned slots = 0;

bool phrase_background_reserve()
{
    portENTER_CRITICAL(&slots_lock);
    bool available = slots < 2;
    if (available) ++slots;
    portEXIT_CRITICAL(&slots_lock);
    return available;
}

void phrase_background_release()
{
    portENTER_CRITICAL(&slots_lock);
    if (slots) --slots;
    portEXIT_CRITICAL(&slots_lock);
}

esp_err_t phrase_background_collect(const char *job_url, const voice_trace_t *trace, ai_response_t *result)
{
    int failures = 0;
    // Deadline is anchored to the original HTTP request, not each polling retry.
    while (esp_timer_get_time() - trace->request_start_us < 180LL * 1000000)
    {
        esp_err_t ret = ai_client_get_job(job_url, trace->request_id, result);
        if (ret == ESP_OK)
        {
            failures = 0;
            if (strcmp(result->job_status, "ready") == 0)
            {
                ESP_LOGI(TAG, "[%s] 后台JSON收到=%lldms | 语音识别=%dms | 大模型响应时间=%dms | 语音合成=%dms",
                         trace->request_id, (esp_timer_get_time() - trace->started_us) / 1000,
                         result->asr_ms, result->dialogue_ms, result->tts_ms);
                ESP_LOGI(TAG, "[%s] 后台服务端：收包=%dms | 音频预处理=%dms | AI流水线=%dms | 首包就绪=%dms | 后台完成=%dms",
                         trace->request_id, result->body_receive_ms, result->prepare_audio_ms,
                         result->total_pipeline_ms, result->total_request_ms, result->background_total_ms);
                if (strcmp(result->tts_status, "ok") != 0 || strstr(result->tts_backend, "fallback"))
                    ESP_LOGW(TAG, "[%s] 后台合成异常/备用音色：%s/%s", trace->request_id, result->tts_status, result->tts_backend);
                return result->audio_url[0] ? ESP_OK : ESP_FAIL;
            }
            if (strcmp(result->job_status, "pending") != 0) return ESP_FAIL;
        }
        else if (++failures >= 3) return ret;
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    return ESP_ERR_TIMEOUT;
}

struct background_context_t
{
    char job_url[80];
    voice_trace_t trace;
};

static void background_task(void *arg)
{
    auto *context = static_cast<background_context_t *>(arg);
    ai_response_t result = {};
    esp_err_t ret = phrase_background_collect(context->job_url, &context->trace, &result);
    if (ret == ESP_OK) ret = audio_reply_download_only(result.audio_url, &context->trace);
    if (ret != ESP_OK)
        ESP_LOGW(TAG, "[%s] 后台生成/下载未完成：%s（不重播）", context->trace.request_id, esp_err_to_name(ret));
    else
        ESP_LOGI(TAG, "[%s] 后台下载完成，音频未播放", context->trace.request_id);
    delete context;
    phrase_background_release();
    vTaskDelete(nullptr);
}

void phrase_background_start(const char *job_url, const voice_trace_t *trace)
{
    auto *context = new (std::nothrow) background_context_t{};
    if (context)
    {
        strlcpy(context->job_url, job_url, sizeof(context->job_url));
        context->trace = *trace; // No pointer into the foreground task's stack.
        context->trace.background_download = true;
        context->trace.cached_playback = false;
        context->trace.download_start_us = context->trace.download_end_us = -1;
        context->trace.playback_start_us = context->trace.playback_end_us = -1;
        if (xTaskCreate(background_task, "phrase_download", 8192, context, 2, nullptr) == pdPASS) return;
        delete context;
    }
    ESP_LOGW(TAG, "[%s] 后台任务内存不足，未下载新音频（不重播）", trace->request_id);
    phrase_background_release();
}

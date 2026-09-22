#include "voice_trace.h"

#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_transport.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "语音";
static portMUX_TYPE watch_lock = portMUX_INITIALIZER_UNLOCKED;
static voice_trace_t *watched_trace = nullptr;
static TaskHandle_t watched_task = nullptr;
static size_t expected_upload_bytes = 0;
static bool body_armed = false;

static long long elapsed_ms(int64_t start, int64_t end)
{
    return start >= 0 && end >= start ? (end - start) / 1000 : -1;
}

void voice_trace_init(voice_trace_t *trace)
{
    *trace = {};
    snprintf(trace->request_id, sizeof(trace->request_id), "esp-%08lx%08lx-%llx",
             (unsigned long)esp_random(), (unsigned long)esp_random(),
             (unsigned long long)esp_timer_get_time());
    trace->started_us = esp_timer_get_time();
    trace->recording_end_us = trace->request_start_us = trace->request_end_us = -1;
    trace->upload_start_us = trace->upload_end_us = trace->json_received_us = -1;
    trace->download_start_us = trace->download_end_us = -1;
    trace->playback_start_us = trace->playback_end_us = -1;
    voice_trace_event(trace, "recording_start", trace->started_us);
}

void voice_trace_event(const voice_trace_t *trace, const char *event, int64_t at_us)
{
    if (trace == nullptr || at_us < 0) return;
    // Pair boundaries into one line; transport writes remain free of log I/O.
    const long long at_ms = elapsed_ms(trace->started_us, at_us);
    if (strcmp(event, "recording_start") == 0)
        ESP_LOGI(TAG, "[%s] 开始监听=0ms（含校准/等待开口；以下时间点相对本轮起点）", trace->request_id);
    else if (strcmp(event, "recording_end") == 0)
        ESP_LOGI(TAG, "[%s] 录音结束=%lldms | 录音流程耗时=%lldms", trace->request_id, at_ms, at_ms);
    else if (strcmp(event, "request_end") == 0)
        ESP_LOGI(TAG, "[%s] 上传开始=%lldms → 上传结束=%lldms | 上传耗时=%lldms | HTTP往返=%lldms | 写入=%u字节/尝试=%u",
                 trace->request_id, elapsed_ms(trace->started_us, trace->upload_start_us),
                 elapsed_ms(trace->started_us, trace->upload_end_us),
                 elapsed_ms(trace->upload_start_us, trace->upload_end_us),
                 elapsed_ms(trace->request_start_us, trace->request_end_us),
                 (unsigned)trace->upload_bytes, trace->upload_attempts);
    else if (strcmp(event, "json_received") == 0)
        ESP_LOGI(TAG, "[%s] 收到JSON=%lldms | 录音结束至JSON=%lldms", trace->request_id, at_ms,
                 elapsed_ms(trace->recording_end_us, at_us));
    else if (strcmp(event, "download_end") == 0)
        ESP_LOGI(TAG, "[%s] 下载开始=%lldms → 下载结束=%lldms | 下载耗时=%lldms", trace->request_id,
                 elapsed_ms(trace->started_us, trace->download_start_us), at_ms,
                 elapsed_ms(trace->download_start_us, at_us));
    else if (strcmp(event, "playback_start") == 0)
        ESP_LOGI(TAG, "[%s] 播放开始=%lldms | 录音结束至播放=%lldms", trace->request_id, at_ms,
                 elapsed_ms(trace->recording_end_us, at_us));
    else if (strcmp(event, "playback_end") == 0)
        ESP_LOGI(TAG, "[%s] 播放结束=%lldms | 播放耗时=%lldms", trace->request_id, at_ms,
                 elapsed_ms(trace->playback_start_us, at_us));
}

void voice_trace_mark(voice_trace_t *trace, const char *event, int64_t *slot)
{
    if (trace == nullptr) return;
    *slot = esp_timer_get_time();
    voice_trace_event(trace, event, *slot);
}

void voice_trace_finish(const voice_trace_t *trace, const char *result)
{
    if (trace == nullptr) return;
    const char *label = result;
    if (strcmp(result, "ok") == 0) label = "完成";
    else if (strcmp(result, "no_speech") == 0) label = "未检测到开口";
    else if (strcmp(result, "no_audio") == 0) label = "未返回音频";
    else if (strcmp(result, "recording_failed") == 0) label = "录音失败";
    else if (strcmp(result, "request_failed") == 0) label = "请求失败";
    else if (strcmp(result, "audio_failed") == 0) label = "下载或播放失败";
    ESP_LOGI(TAG, "[%s] 本轮结果=%s(%s) | 录音结束至播放结束=%lldms（-1=未到达）",
             trace->request_id, label, result, elapsed_ms(trace->recording_end_us, trace->playback_end_us));
}

bool voice_trace_watch_upload(voice_trace_t *trace, size_t expected_bytes)
{
    if (trace == nullptr) return false;
    portENTER_CRITICAL(&watch_lock);
    bool available = watched_trace == nullptr;
    if (available)
    {
        watched_trace = trace;
        watched_task = xTaskGetCurrentTaskHandle();
        expected_upload_bytes = expected_bytes;
        body_armed = false;
    }
    portEXIT_CRITICAL(&watch_lock);
    return available;
}

void voice_trace_upload_headers_sent(voice_trace_t *trace)
{
    portENTER_CRITICAL(&watch_lock);
    if (trace != nullptr && trace == watched_trace && watched_task == xTaskGetCurrentTaskHandle())
    {
        // Redirect/auth retry: record the last attempt and expose attempt count.
        trace->upload_attempts++;
        trace->upload_bytes = 0;
        trace->upload_start_us = trace->upload_end_us = -1;
        body_armed = true;
    }
    portEXIT_CRITICAL(&watch_lock);
}

void voice_trace_unwatch_upload(voice_trace_t *trace)
{
    portENTER_CRITICAL(&watch_lock);
    if (trace != nullptr && trace == watched_trace && watched_task == xTaskGetCurrentTaskHandle())
    {
        watched_trace = nullptr;
        watched_task = nullptr;
        body_armed = false;
    }
    portEXIT_CRITICAL(&watch_lock);
}

// IDF 5.5 has HEADERS_SENT but no request-body-sent event. This transparent
// linker wrapper measures positive transport write returns AFTER HEADERS_SENT.
// It forwards the original args/result exactly once. No log I/O inside writes.
extern "C" int __real_esp_transport_write(esp_transport_handle_t t, const char *buffer, int len, int timeout_ms);
extern "C" int __wrap_esp_transport_write(esp_transport_handle_t t, const char *buffer, int len, int timeout_ms)
{
    portENTER_CRITICAL(&watch_lock);
    voice_trace_t *trace = body_armed && watched_task == xTaskGetCurrentTaskHandle() ? watched_trace : nullptr;
    portEXIT_CRITICAL(&watch_lock);
    int64_t before = trace ? esp_timer_get_time() : -1;
    int written = __real_esp_transport_write(t, buffer, len, timeout_ms);
    int64_t after = trace ? esp_timer_get_time() : -1;
    if (trace)
    {
        portENTER_CRITICAL(&watch_lock);
        if (trace == watched_trace && body_armed)
        {
            if (trace->upload_start_us < 0) trace->upload_start_us = before;
            if (written > 0) trace->upload_bytes += (size_t)written;
            if (trace->upload_bytes >= expected_upload_bytes)
            {
                trace->upload_end_us = after;
                body_armed = false;
            }
        }
        portEXIT_CRITICAL(&watch_lock);
    }
    return written;
}

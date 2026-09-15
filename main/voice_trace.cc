#include "voice_trace.h"

#include <stdio.h>
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_transport.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "voice_trace";
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
    ESP_LOGI(TAG, "VOICE_TRACE id=%s event=%s t_us=%lld since_start_ms=%lld",
             trace->request_id, event, (long long)at_us, elapsed_ms(trace->started_us, at_us));
}

void voice_trace_mark(voice_trace_t *trace, const char *event, int64_t *slot)
{
    if (trace == nullptr) return;
    *slot = esp_timer_get_time();
    voice_trace_event(trace, event, *slot);
}

void voice_trace_finish(const voice_trace_t *trace, const char *result)
{
    ESP_LOGI(TAG,
             "VOICE_SUMMARY id=%s result=%s record_call_ms=%lld request_ms=%lld upload_ms=%lld "
             "upload_bytes=%u upload_attempts=%u download_ms=%lld playback_call_ms=%lld "
             "record_end_to_json_ms=%lld record_end_to_play_start_ms=%lld record_end_to_play_end_ms=%lld",
             trace->request_id, result, elapsed_ms(trace->started_us, trace->recording_end_us),
             elapsed_ms(trace->request_start_us, trace->request_end_us),
             elapsed_ms(trace->upload_start_us, trace->upload_end_us),
             (unsigned)trace->upload_bytes, trace->upload_attempts,
             elapsed_ms(trace->download_start_us, trace->download_end_us),
             elapsed_ms(trace->playback_start_us, trace->playback_end_us),
             elapsed_ms(trace->recording_end_us, trace->json_received_us),
             elapsed_ms(trace->recording_end_us, trace->playback_start_us),
             elapsed_ms(trace->recording_end_us, trace->playback_end_us));
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

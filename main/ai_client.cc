#include "ai_client.h"

#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <memory>
#include <new>
#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "network_config.h"

static const char *TAG = "ai_client";
static const int HTTP_TIMEOUT_MS = 20000;
static const int RESPONSE_BUFFER_SIZE = 8192;

typedef struct
{
    char *buffer;
    int len;
    int capacity;
    voice_trace_t *trace;
    int64_t finished_us;
    bool truncated;
    int correlation; // -1: old server/no header, 0: mismatch, 1: matched.
} response_buffer_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    response_buffer_t *response = (response_buffer_t *)evt->user_data;

    if (response != nullptr && evt->event_id == HTTP_EVENT_HEADERS_SENT)
        voice_trace_upload_headers_sent(response->trace);
    if (response != nullptr && evt->event_id == HTTP_EVENT_ON_FINISH)
        response->finished_us = esp_timer_get_time();
    if (response != nullptr && evt->event_id == HTTP_EVENT_ON_HEADER &&
        strcasecmp(evt->header_key, "X-Request-ID") == 0 && response->trace != nullptr)
        response->correlation = strcmp(response->trace->request_id, evt->header_value) == 0 ? 1 : 0;

    if (evt->event_id == HTTP_EVENT_ON_DATA && response != nullptr && evt->data_len > 0)
    {
        int copy_len = evt->data_len;
        if (response->len + copy_len >= response->capacity)
        {
            response->truncated = true;
            copy_len = response->capacity - response->len - 1;
        }
        if (copy_len > 0)
        {
            memcpy(response->buffer + response->len, evt->data, copy_len);
            response->len += copy_len;
            response->buffer[response->len] = '\0';
        }
    }

    return ESP_OK;
}

static void copy_json_string(cJSON *root, const char *key, char *dst, size_t dst_len)
{
    cJSON *item = cJSON_GetObjectItem(root, key);
    if (cJSON_IsString(item) && item->valuestring != nullptr)
    {
        strlcpy(dst, item->valuestring, dst_len);
    }
}

static int copy_json_integer(cJSON *root, const char *key)
{
    cJSON *item = cJSON_GetObjectItem(root, key);
    return cJSON_IsNumber(item) ? item->valueint : -1;
}

static void parse_response(cJSON *root, ai_response_t *response)
{
    memset(response, 0, sizeof(*response));
    copy_json_string(root, "reply_text", response->reply_text, sizeof(response->reply_text));
    copy_json_string(root, "recognized_text", response->recognized_text, sizeof(response->recognized_text));
    copy_json_string(root, "asr_status", response->asr_status, sizeof(response->asr_status));
    copy_json_string(root, "asr_backend", response->asr_backend, sizeof(response->asr_backend));
    copy_json_string(root, "llm_status", response->llm_status, sizeof(response->llm_status));
    copy_json_string(root, "llm_backend", response->llm_backend, sizeof(response->llm_backend));
    copy_json_string(root, "tts_status", response->tts_status, sizeof(response->tts_status));
    copy_json_string(root, "tts_backend", response->tts_backend, sizeof(response->tts_backend));
    copy_json_string(root, "motion", response->motion, sizeof(response->motion));
    copy_json_string(root, "audio_url", response->audio_url, sizeof(response->audio_url));
    copy_json_string(root, "job_url", response->job_url, sizeof(response->job_url));
    copy_json_string(root, "job_status", response->job_status, sizeof(response->job_status));
    response->phrase_hit = cJSON_IsTrue(cJSON_GetObjectItem(root, "phrase_hit"));
    cJSON *timings = cJSON_GetObjectItem(root, "timings_ms");
    response->asr_ms = copy_json_integer(timings, "asr");
    response->dialogue_ms = copy_json_integer(timings, "dialogue");
    response->tts_ms = copy_json_integer(timings, "tts");
    response->total_pipeline_ms = copy_json_integer(timings, "total_pipeline");
    response->body_receive_ms = copy_json_integer(timings, "body_receive");
    response->prepare_audio_ms = copy_json_integer(timings, "prepare_audio");
    response->total_request_ms = copy_json_integer(timings, "total_request");
    response->background_total_ms = copy_json_integer(timings, "background_total");
}

esp_err_t ai_client_send_pcm(const int16_t *samples, size_t byte_len, uint32_t sample_rate, ai_response_t *response,
                             voice_trace_t *trace, bool allow_phrase_cache)
{
    if (samples == nullptr || byte_len == 0 || response == nullptr)
    {
        return ESP_ERR_INVALID_ARG;
    }

    memset(response, 0, sizeof(*response));
    response->asr_ms = response->dialogue_ms = response->tts_ms = response->total_pipeline_ms = -1;
    response->body_receive_ms = response->prepare_audio_ms = response->total_request_ms = -1;

    // Keep the larger, bounded protocol buffer off the audio task's stack.
    std::unique_ptr<char[]> response_storage(new (std::nothrow) char[RESPONSE_BUFFER_SIZE]());
    if (!response_storage) return ESP_ERR_NO_MEM;
    response_buffer_t response_buffer = {
        .buffer = response_storage.get(),
        .len = 0,
        .capacity = RESPONSE_BUFFER_SIZE,
        .trace = trace,
        .finished_us = -1,
        .truncated = false,
        .correlation = -1,
    };

    esp_http_client_config_t config = {};
    config.url = AI_SERVER_URL;
    config.timeout_ms = HTTP_TIMEOUT_MS;
    config.event_handler = http_event_handler;
    config.user_data = &response_buffer;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == nullptr)
    {
        return ESP_FAIL;
    }

    char sample_rate_header[16];
    snprintf(sample_rate_header, sizeof(sample_rate_header), "%lu", (unsigned long)sample_rate);

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", "application/octet-stream");
    esp_http_client_set_header(client, "X-Audio-Format", "pcm_s16le_mono");
    esp_http_client_set_header(client, "X-Sample-Rate", sample_rate_header);
    if (allow_phrase_cache) esp_http_client_set_header(client, "X-Voice-Capabilities", "phrase-cache-v1");
    if (trace) esp_http_client_set_header(client, "X-Request-ID", trace->request_id);
    esp_http_client_set_post_field(client, (const char *)samples, byte_len);

    if (trace) voice_trace_mark(trace, "request_start", &trace->request_start_us);
    bool watching = voice_trace_watch_upload(trace, byte_len);
    esp_err_t ret = esp_http_client_perform(client);
    int64_t request_end_us = esp_timer_get_time();
    if (watching) voice_trace_unwatch_upload(trace);
    if (trace)
    {
        trace->request_end_us = request_end_us;
        // Emitted after perform to keep serial logging out of the upload writes.
        voice_trace_event(trace, "request_end", trace->request_end_us);
        if (response_buffer.correlation != 1 || response_buffer.truncated || !watching)
            ESP_LOGW(TAG, "[%s] HTTP观测异常：编号匹配=%d(-1=无回显) | JSON截断=%d | 上传观测=%d | HTTP=%d",
                     trace->request_id, response_buffer.correlation, response_buffer.truncated, watching,
                     esp_http_client_get_status_code(client));
    }
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "[%s] HTTP请求失败：%s", trace ? trace->request_id : "-", esp_err_to_name(ret));
        esp_http_client_cleanup(client);
        return ret;
    }

    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (status < 200 || status >= 300)
    {
        ESP_LOGE(TAG, "[%s] 服务器返回HTTP错误：%d", trace ? trace->request_id : "-", status);
        return ESP_FAIL;
    }

    cJSON *root = response_buffer.truncated ? nullptr : cJSON_Parse(response_storage.get());
    if (root == nullptr)
    {
        ESP_LOGE(TAG, "[%s] JSON解析失败：收到%d字节，截断=%d", trace ? trace->request_id : "-",
                 response_buffer.len, response_buffer.truncated);
        return ESP_FAIL;
    }
    if (trace)
    {
        trace->json_received_us = response_buffer.finished_us;
        voice_trace_event(trace, "json_received", trace->json_received_us);
    }

    parse_response(root, response);
    cJSON_Delete(root);
    if (response->phrase_hit && (!allow_phrase_cache || response->job_url[0] == '\0' || response->audio_url[0] == '\0'))
        return ESP_ERR_INVALID_RESPONSE;

    return ESP_OK;
}

esp_err_t ai_client_get_job(const char *job_url, const char *request_id, ai_response_t *response)
{
    // Only job paths issued by this protocol, always on the configured origin.
    const char *prefix = "/voice/jobs/";
    if (!job_url || !request_id || !response || strncmp(job_url, prefix, strlen(prefix)) != 0 ||
        strlen(job_url) != strlen(prefix) + 32 || strspn(job_url + strlen(prefix), "0123456789abcdef") != 32)
        return ESP_ERR_INVALID_ARG;
    // Bind the macro once: repeated string literals need not share an address.
    const char *server_url = AI_SERVER_URL;
    const char *scheme = strstr(server_url, "://");
    if (!scheme) return ESP_ERR_INVALID_ARG;
    const char *path = strchr(scheme + 3, '/');
    size_t origin_len = path ? (size_t)(path - server_url) : strlen(server_url);
    char url[256];
    if (origin_len + strlen(job_url) >= sizeof(url)) return ESP_ERR_INVALID_ARG;
    snprintf(url, sizeof(url), "%.*s%s", (int)origin_len, server_url, job_url);
    std::unique_ptr<char[]> storage(new (std::nothrow) char[RESPONSE_BUFFER_SIZE]());
    if (!storage) return ESP_ERR_NO_MEM;
    voice_trace_t correlation_trace = {};
    strlcpy(correlation_trace.request_id, request_id, sizeof(correlation_trace.request_id));
    response_buffer_t buffer = {storage.get(), 0, RESPONSE_BUFFER_SIZE, &correlation_trace, -1, false, -1};
    esp_http_client_config_t config = {};
    config.url = url;
    config.timeout_ms = 25000; // Server long-polls up to 20s, asynchronously.
    config.event_handler = http_event_handler;
    config.user_data = &buffer;
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return ESP_FAIL;
    esp_http_client_set_header(client, "X-Request-ID", request_id);
    esp_err_t ret = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    if (ret != ESP_OK) return ret;
    if (status != 200 || buffer.truncated || buffer.correlation != 1) return ESP_ERR_INVALID_RESPONSE;
    cJSON *json = cJSON_Parse(storage.get());
    if (!json) return ESP_ERR_INVALID_RESPONSE;
    parse_response(json, response);
    cJSON_Delete(json);
    return ESP_OK;
}

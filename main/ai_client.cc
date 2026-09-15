#include "ai_client.h"

#include <stdio.h>
#include <string.h>
#include <strings.h>
#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "network_config.h"

static const char *TAG = "ai_client";
static const int HTTP_TIMEOUT_MS = 20000;
static const int RESPONSE_BUFFER_SIZE = 2048;

typedef struct
{
    char *buffer;
    int len;
    int capacity;
    voice_trace_t *trace;
    int64_t finished_us;
    bool truncated;
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
        ESP_LOGI(TAG, "VOICE_CORRELATION id=%s server_id=%s match=%d", response->trace->request_id,
                 evt->header_value, strcmp(response->trace->request_id, evt->header_value) == 0);

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

esp_err_t ai_client_send_pcm(const int16_t *samples, size_t byte_len, uint32_t sample_rate, ai_response_t *response,
                             voice_trace_t *trace)
{
    if (samples == nullptr || byte_len == 0 || response == nullptr)
    {
        return ESP_ERR_INVALID_ARG;
    }

    memset(response, 0, sizeof(*response));
    response->asr_ms = response->dialogue_ms = response->tts_ms = response->total_pipeline_ms = -1;
    response->body_receive_ms = response->prepare_audio_ms = response->total_request_ms = -1;

    char response_storage[RESPONSE_BUFFER_SIZE] = {};
    response_buffer_t response_buffer = {
        .buffer = response_storage,
        .len = 0,
        .capacity = RESPONSE_BUFFER_SIZE,
        .trace = trace,
        .finished_us = -1,
        .truncated = false,
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
    if (trace) esp_http_client_set_header(client, "X-Request-ID", trace->request_id);
    esp_http_client_set_post_field(client, (const char *)samples, byte_len);

    ESP_LOGI(TAG, "Uploading PCM to AI server: %u bytes -> %s", (unsigned)byte_len, AI_SERVER_URL);
    if (trace) voice_trace_mark(trace, "request_start", &trace->request_start_us);
    bool watching = voice_trace_watch_upload(trace, byte_len);
    esp_err_t ret = esp_http_client_perform(client);
    int64_t request_end_us = esp_timer_get_time();
    if (watching) voice_trace_unwatch_upload(trace);
    if (trace)
    {
        trace->request_end_us = request_end_us;
        // Emitted after perform to keep serial logging out of the upload writes.
        voice_trace_event(trace, "upload_start", trace->upload_start_us);
        voice_trace_event(trace, "upload_end", trace->upload_end_us);
        voice_trace_event(trace, "request_end", trace->request_end_us);
        ESP_LOGI(TAG, "VOICE_HTTP id=%s ret=%s status=%d response_bytes=%d truncated=%d upload_observed=%d",
                 trace->request_id, esp_err_to_name(ret), esp_http_client_get_status_code(client),
                 response_buffer.len, response_buffer.truncated, watching);
    }
    if (ret != ESP_OK)
    {
        ESP_LOGE(TAG, "HTTP request failed: %s", esp_err_to_name(ret));
        esp_http_client_cleanup(client);
        return ret;
    }

    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (status < 200 || status >= 300)
    {
        ESP_LOGE(TAG, "AI server returned HTTP status %d", status);
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(response_storage);
    if (root == nullptr)
    {
        ESP_LOGE(TAG, "Failed to parse AI server JSON: %s", response_storage);
        return ESP_FAIL;
    }
    if (trace)
    {
        trace->json_received_us = response_buffer.finished_us;
        voice_trace_event(trace, "json_received", trace->json_received_us);
        voice_trace_event(trace, "json_parsed", esp_timer_get_time());
    }

    copy_json_string(root, "reply_text", response->reply_text, sizeof(response->reply_text));
    copy_json_string(root, "recognized_text", response->recognized_text, sizeof(response->recognized_text));
    copy_json_string(root, "asr_status", response->asr_status, sizeof(response->asr_status));
    copy_json_string(root, "asr_backend", response->asr_backend, sizeof(response->asr_backend));
    copy_json_string(root, "motion", response->motion, sizeof(response->motion));
    copy_json_string(root, "audio_url", response->audio_url, sizeof(response->audio_url));
    cJSON *timings = cJSON_GetObjectItem(root, "timings_ms");
    if (cJSON_IsObject(timings))
    {
        response->asr_ms = copy_json_integer(timings, "asr");
        response->dialogue_ms = copy_json_integer(timings, "dialogue");
        response->tts_ms = copy_json_integer(timings, "tts");
        response->total_pipeline_ms = copy_json_integer(timings, "total_pipeline");
        response->body_receive_ms = copy_json_integer(timings, "body_receive");
        response->prepare_audio_ms = copy_json_integer(timings, "prepare_audio");
        response->total_request_ms = copy_json_integer(timings, "total_request");
    }
    cJSON_Delete(root);

    ESP_LOGI(TAG, "AI reply: recognized='%s', asr_status='%s', asr_backend='%s', text='%s', motion='%s', audio_url='%s', server_ms=%d",
             response->recognized_text, response->asr_status, response->asr_backend,
             response->reply_text, response->motion, response->audio_url, response->total_pipeline_ms);
    return ESP_OK;
}

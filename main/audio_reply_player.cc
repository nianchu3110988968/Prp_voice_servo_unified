#include "audio_reply_player.h"

#include <string.h>
#include "bsp_board.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "network_config.h"

static const char *TAG = "audio_reply_player";
static const int HTTP_TIMEOUT_MS = 20000;
static const size_t MAX_AUDIO_BYTES = 512 * 1024;

typedef struct
{
    uint8_t *data;
    size_t len;
    size_t capacity;
} download_buffer_t;

static esp_err_t download_event_handler(esp_http_client_event_t *evt)
{
    download_buffer_t *buffer = (download_buffer_t *)evt->user_data;
    if (evt->event_id != HTTP_EVENT_ON_DATA || buffer == nullptr || evt->data_len <= 0)
    {
        return ESP_OK;
    }

    if (buffer->len + evt->data_len > buffer->capacity)
    {
        ESP_LOGE(TAG, "Downloaded audio exceeds buffer: %u > %u",
                 (unsigned)(buffer->len + evt->data_len), (unsigned)buffer->capacity);
        return ESP_FAIL;
    }

    memcpy(buffer->data + buffer->len, evt->data, evt->data_len);
    buffer->len += evt->data_len;
    return ESP_OK;
}

static bool build_absolute_url(const char *audio_url, char *dst, size_t dst_len)
{
    if (audio_url == nullptr || audio_url[0] == '\0')
    {
        return false;
    }

    if (strncmp(audio_url, "http://", 7) == 0 || strncmp(audio_url, "https://", 8) == 0)
    {
        strlcpy(dst, audio_url, dst_len);
        return true;
    }

    const char *scheme_end = strstr(AI_SERVER_URL, "://");
    if (scheme_end == nullptr)
    {
        return false;
    }

    const char *host_start = scheme_end + 3;
    const char *path_start = strchr(host_start, '/');
    size_t origin_len = path_start == nullptr ? strlen(AI_SERVER_URL) : (size_t)(path_start - AI_SERVER_URL);
    if (origin_len + strlen(audio_url) + 1 > dst_len)
    {
        return false;
    }

    memcpy(dst, AI_SERVER_URL, origin_len);
    dst[origin_len] = '\0';
    strlcat(dst, audio_url[0] == '/' ? audio_url : "/", dst_len);
    if (audio_url[0] != '/')
    {
        strlcat(dst, audio_url, dst_len);
    }
    return true;
}

static uint32_t read_le32(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
}

static bool find_wav_data_chunk(const uint8_t *wav, size_t wav_len, const uint8_t **pcm, size_t *pcm_len)
{
    if (wav_len < 44 || memcmp(wav, "RIFF", 4) != 0 || memcmp(wav + 8, "WAVE", 4) != 0)
    {
        return false;
    }

    size_t offset = 12;
    while (offset + 8 <= wav_len)
    {
        const uint8_t *chunk = wav + offset;
        uint32_t chunk_size = read_le32(chunk + 4);
        offset += 8;

        if (offset + chunk_size > wav_len)
        {
            return false;
        }

        if (memcmp(chunk, "data", 4) == 0)
        {
            *pcm = wav + offset;
            *pcm_len = chunk_size;
            return true;
        }

        offset += chunk_size + (chunk_size & 1);
    }

    return false;
}

esp_err_t audio_reply_play_from_url(const char *audio_url, voice_trace_t *trace)
{
    char full_url[256];
    if (!build_absolute_url(audio_url, full_url, sizeof(full_url)))
    {
        ESP_LOGW(TAG, "No valid reply audio URL to play");
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t *storage = (uint8_t *)heap_caps_malloc(MAX_AUDIO_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (storage == nullptr)
    {
        storage = (uint8_t *)heap_caps_malloc(MAX_AUDIO_BYTES, MALLOC_CAP_8BIT);
    }
    if (storage == nullptr)
    {
        ESP_LOGE(TAG, "Failed to allocate reply audio buffer");
        return ESP_ERR_NO_MEM;
    }

    download_buffer_t buffer = {
        .data = storage,
        .len = 0,
        .capacity = MAX_AUDIO_BYTES,
    };

    esp_http_client_config_t config = {};
    config.url = full_url;
    config.timeout_ms = HTTP_TIMEOUT_MS;
    config.event_handler = download_event_handler;
    config.user_data = &buffer;

    int64_t download_start_us = esp_timer_get_time();
    ESP_LOGI(TAG, "Downloading reply audio: %s", full_url);
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == nullptr)
    {
        heap_caps_free(storage);
        return ESP_FAIL;
    }

    if (trace)
    {
        esp_http_client_set_header(client, "X-Request-ID", trace->request_id);
        voice_trace_mark(trace, "download_start", &trace->download_start_us);
    }
    esp_err_t ret = esp_http_client_perform(client);
    if (trace) voice_trace_mark(trace, "download_end", &trace->download_end_us);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    int download_ms = (int)((esp_timer_get_time() - download_start_us) / 1000);
    if (trace) ESP_LOGI(TAG, "VOICE_DOWNLOAD id=%s ret=%s status=%d bytes=%u",
                       trace->request_id, esp_err_to_name(ret), status, (unsigned)buffer.len);
    if (ret != ESP_OK || status < 200 || status >= 300)
    {
        ESP_LOGE(TAG, "Reply audio download failed: ret=%s, status=%d", esp_err_to_name(ret), status);
        heap_caps_free(storage);
        return ret == ESP_OK ? ESP_FAIL : ret;
    }

    const uint8_t *pcm = nullptr;
    size_t pcm_len = 0;
    if (!find_wav_data_chunk(storage, buffer.len, &pcm, &pcm_len))
    {
        ESP_LOGE(TAG, "Reply audio is not a supported PCM WAV, bytes=%u", (unsigned)buffer.len);
        heap_caps_free(storage);
        return ESP_ERR_INVALID_RESPONSE;
    }

    ESP_LOGI(TAG, "Reply audio downloaded: wav=%u bytes, pcm=%u bytes, download_ms=%d",
             (unsigned)buffer.len, (unsigned)pcm_len, download_ms);
    ESP_LOGI(TAG, "Reply audio playback starting");
    if (trace) voice_trace_mark(trace, "playback_start", &trace->playback_start_us);
    ret = bsp_play_audio(pcm, pcm_len);
    if (trace) voice_trace_mark(trace, "playback_end", &trace->playback_end_us);
    ESP_LOGI(TAG, "Reply audio playback finished: %s", esp_err_to_name(ret));

    heap_caps_free(storage);
    return ret;
}

#include "audio_reply_player.h"

#include <string.h>
#include "bsp_board.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "network_config.h"

static const char *TAG = "audio_reply_player";
static const int HTTP_TIMEOUT_MS = 20000;
static const size_t MAX_AUDIO_BYTES = 512 * 1024;

typedef struct
{
    uint8_t *data;
    size_t len;
    size_t capacity;
    bool overflow;
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
        buffer->overflow = true;
        ESP_LOGE(TAG, "Downloaded audio exceeds buffer: %u > %u",
                 (unsigned)(buffer->len + evt->data_len), (unsigned)buffer->capacity);
        return ESP_FAIL;
    }

    // Background downloads consume real network bytes, without a second 512KB
    // allocation and without ever calling the audio driver.
    if (buffer->data) memcpy(buffer->data + buffer->len, evt->data, evt->data_len);
    buffer->len += evt->data_len;
    return ESP_OK;
}

static bool build_absolute_url(const char *audio_url, char *dst, size_t dst_len)
{
    if (audio_url == nullptr || audio_url[0] == '\0' || dst == nullptr || dst_len == 0)
    {
        return false;
    }

    if (strncmp(audio_url, "http://", 7) == 0 || strncmp(audio_url, "https://", 8) == 0)
    {
        if (strlen(audio_url) >= dst_len) return false;
        strlcpy(dst, audio_url, dst_len);
        return true;
    }

    // A macro expanding to a string literal may create a distinct array at each
    // use (e.g. MSVC /GF-). Subtract pointers only within this one bound array.
    const char *server_url = AI_SERVER_URL;
    const char *scheme_end = strstr(server_url, "://");
    if (scheme_end == nullptr)
    {
        return false;
    }

    const char *host_start = scheme_end + 3;
    const char *path_start = strchr(host_start, '/');
    size_t origin_len = path_start == nullptr ? strlen(server_url) : (size_t)(path_start - server_url);
    size_t separator_len = audio_url[0] == '/' ? 0 : 1;
    if (origin_len + separator_len + strlen(audio_url) + 1 > dst_len)
    {
        return false;
    }

    memcpy(dst, server_url, origin_len);
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

static esp_err_t download_reply(const char *audio_url, voice_trace_t *trace, bool play)
{
    char full_url[256];
    if (!build_absolute_url(audio_url, full_url, sizeof(full_url)))
    {
        ESP_LOGW(TAG, "No valid reply audio URL to play");
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t *storage = play ? (uint8_t *)heap_caps_malloc(MAX_AUDIO_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) : nullptr;
    if (play && storage == nullptr)
    {
        storage = (uint8_t *)heap_caps_malloc(MAX_AUDIO_BYTES, MALLOC_CAP_8BIT);
    }
    if (play && storage == nullptr)
    {
        ESP_LOGE(TAG, "Failed to allocate reply audio buffer");
        return ESP_ERR_NO_MEM;
    }

    download_buffer_t buffer = {
        .data = storage,
        .len = 0,
        .capacity = MAX_AUDIO_BYTES,
        .overflow = false,
    };

    esp_http_client_config_t config = {};
    config.url = full_url;
    config.timeout_ms = HTTP_TIMEOUT_MS;
    config.event_handler = download_event_handler;
    config.user_data = &buffer;

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

    if (ret != ESP_OK || status < 200 || status >= 300 || buffer.overflow || buffer.len == 0)
    {
        ESP_LOGE(TAG, "[%s] 音频下载失败：%s，HTTP=%d，已收=%u字节",
                 trace ? trace->request_id : "-", esp_err_to_name(ret), status, (unsigned)buffer.len);
        heap_caps_free(storage);
        return ret == ESP_OK ? ESP_FAIL : ret;
    }

    if (!play) return ESP_OK;

    const uint8_t *pcm = nullptr;
    size_t pcm_len = 0;
    if (!find_wav_data_chunk(storage, buffer.len, &pcm, &pcm_len))
    {
        ESP_LOGE(TAG, "Reply audio is not a supported PCM WAV, bytes=%u", (unsigned)buffer.len);
        heap_caps_free(storage);
        return ESP_ERR_INVALID_RESPONSE;
    }

    if (trace) voice_trace_mark(trace, "playback_start", &trace->playback_start_us);
    ret = bsp_play_audio(pcm, pcm_len);
    if (trace) voice_trace_mark(trace, "playback_end", &trace->playback_end_us);
    if (ret != ESP_OK)
        ESP_LOGE(TAG, "[%s] 播放失败：%s", trace ? trace->request_id : "-", esp_err_to_name(ret));

    heap_caps_free(storage);
    return ret;
}

esp_err_t audio_reply_play_from_url(const char *audio_url, voice_trace_t *trace)
{
    return download_reply(audio_url, trace, true);
}

esp_err_t audio_reply_download_only(const char *audio_url, voice_trace_t *trace)
{
    return download_reply(audio_url, trace, false);
}

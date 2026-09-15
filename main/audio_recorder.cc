#include "audio_recorder.h"

#include <string.h>
#include "bsp_board.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "network_config.h"

static const char *TAG = "audio_recorder";
static const uint32_t SAMPLE_RATE_HZ = 16000;
static const uint32_t BYTES_PER_SAMPLE = sizeof(int16_t);

typedef struct
{
    uint32_t peak;
    uint32_t rms;
} frame_audio_stats_t;

static uint32_t isqrt_u64(uint64_t value)
{
    uint64_t low = 0;
    uint64_t high = 65535;
    while (low <= high)
    {
        uint64_t mid = (low + high) / 2;
        uint64_t square = mid * mid;
        if (square == value)
        {
            return (uint32_t)mid;
        }
        if (square < value)
        {
            low = mid + 1;
        }
        else
        {
            high = mid - 1;
        }
    }
    return (uint32_t)high;
}

static uint32_t frame_duration_ms(int frame_bytes)
{
    uint32_t bytes_per_second = SAMPLE_RATE_HZ * BYTES_PER_SAMPLE;
    uint32_t duration = ((uint32_t)frame_bytes * 1000) / bytes_per_second;
    return duration > 0 ? duration : 1;
}

static size_t aligned_bytes_for_duration(uint32_t duration_ms, int frame_bytes)
{
    size_t bytes = (SAMPLE_RATE_HZ * BYTES_PER_SAMPLE * duration_ms) / 1000;
    return (bytes / frame_bytes) * frame_bytes;
}

static uint32_t max_u32(uint32_t a, uint32_t b)
{
    return a > b ? a : b;
}

static uint32_t dynamic_start_threshold(uint32_t noise_floor)
{
    uint32_t with_margin = noise_floor + AI_RECORD_START_NOISE_MARGIN;
    uint32_t scaled = (noise_floor * AI_RECORD_START_NOISE_MULTIPLIER_PERCENT) / 100;
    return max_u32(AI_RECORD_START_RMS_THRESHOLD, max_u32(with_margin, scaled));
}

static uint32_t dynamic_stop_threshold(uint32_t noise_floor)
{
    uint32_t with_margin = noise_floor + AI_RECORD_STOP_NOISE_MARGIN;
    uint32_t scaled = (noise_floor * AI_RECORD_STOP_NOISE_MULTIPLIER_PERCENT) / 100;
    return max_u32(AI_RECORD_STOP_RMS_THRESHOLD, max_u32(with_margin, scaled));
}

static void apply_recording_gain(int16_t *samples, size_t sample_count)
{
    if (AI_RECORD_GAIN <= 1)
    {
        return;
    }

    for (size_t i = 0; i < sample_count; i++)
    {
        int32_t amplified = (int32_t)samples[i] * AI_RECORD_GAIN;
        if (amplified > 32767)
        {
            amplified = 32767;
        }
        else if (amplified < -32768)
        {
            amplified = -32768;
        }
        samples[i] = (int16_t)amplified;
    }
}

static frame_audio_stats_t calculate_frame_stats(const int16_t *samples, size_t sample_count)
{
    frame_audio_stats_t stats = {};
    uint64_t sum_squares = 0;

    for (size_t i = 0; i < sample_count; i++)
    {
        int32_t sample = samples[i];
        uint32_t abs_sample = sample < 0 ? (uint32_t)(-sample) : (uint32_t)sample;
        if (abs_sample > stats.peak)
        {
            stats.peak = abs_sample;
        }
        sum_squares += (uint64_t)sample * (uint64_t)sample;
    }

    if (sample_count > 0)
    {
        stats.rms = isqrt_u64(sum_squares / sample_count);
    }
    return stats;
}

static bool append_audio_frame(uint8_t *dst, size_t dst_capacity, size_t *dst_len, const uint8_t *frame, size_t frame_bytes)
{
    if (*dst_len + frame_bytes > dst_capacity)
    {
        return false;
    }
    memcpy(dst + *dst_len, frame, frame_bytes);
    *dst_len += frame_bytes;
    return true;
}

esp_err_t audio_recorder_record_pcm(audio_recording_t *recording, uint32_t duration_ms, int frame_bytes)
{
    if (recording == nullptr || frame_bytes <= 0)
    {
        return ESP_ERR_INVALID_ARG;
    }

    memset(recording, 0, sizeof(*recording));

    size_t target_bytes = (SAMPLE_RATE_HZ * BYTES_PER_SAMPLE * duration_ms) / 1000;
    target_bytes = (target_bytes / frame_bytes) * frame_bytes;
    if (target_bytes == 0)
    {
        return ESP_ERR_INVALID_ARG;
    }

    int16_t *buffer = (int16_t *)heap_caps_malloc(target_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (buffer == nullptr)
    {
        buffer = (int16_t *)heap_caps_malloc(target_bytes, MALLOC_CAP_8BIT);
    }
    if (buffer == nullptr)
    {
        ESP_LOGE(TAG, "Failed to allocate recording buffer: %u bytes", (unsigned)target_bytes);
        return ESP_ERR_NO_MEM;
    }

    uint8_t *write_ptr = (uint8_t *)buffer;
    size_t remaining = target_bytes;
    while (remaining >= (size_t)frame_bytes)
    {
        esp_err_t ret = bsp_get_feed_data(false, (int16_t *)write_ptr, frame_bytes);
        if (ret != ESP_OK)
        {
            heap_caps_free(buffer);
            ESP_LOGE(TAG, "Failed to read microphone frame: %s", esp_err_to_name(ret));
            return ret;
        }
        write_ptr += frame_bytes;
        remaining -= frame_bytes;
    }

    apply_recording_gain(buffer, target_bytes / BYTES_PER_SAMPLE);

    recording->samples = buffer;
    recording->byte_len = target_bytes;
    recording->sample_rate = SAMPLE_RATE_HZ;
    recording->duration_ms = duration_ms;
    ESP_LOGI(TAG, "Recorded PCM audio: %u bytes, %u ms, gain=%d",
             (unsigned)target_bytes, (unsigned)duration_ms, AI_RECORD_GAIN);
    return ESP_OK;
}

esp_err_t audio_recorder_record_pcm_endpoint(audio_recording_t *recording, int frame_bytes, uint32_t start_timeout_ms)
{
    if (recording == nullptr || frame_bytes <= 0 || (frame_bytes % (int)BYTES_PER_SAMPLE) != 0)
    {
        return ESP_ERR_INVALID_ARG;
    }

    memset(recording, 0, sizeof(*recording));

    size_t max_bytes = aligned_bytes_for_duration(AI_RECORD_MAX_DURATION_MS, frame_bytes);
    size_t min_bytes = aligned_bytes_for_duration(AI_RECORD_MIN_DURATION_MS, frame_bytes);
    size_t preroll_bytes = aligned_bytes_for_duration(AI_RECORD_PREROLL_MS, frame_bytes);
    if (max_bytes == 0)
    {
        return ESP_ERR_INVALID_ARG;
    }
    if (min_bytes == 0)
    {
        min_bytes = frame_bytes;
    }
    if (preroll_bytes == 0 && AI_RECORD_PREROLL_MS > 0)
    {
        preroll_bytes = frame_bytes;
    }

    int16_t *buffer = (int16_t *)heap_caps_malloc(max_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (buffer == nullptr)
    {
        buffer = (int16_t *)heap_caps_malloc(max_bytes, MALLOC_CAP_8BIT);
    }
    if (buffer == nullptr)
    {
        ESP_LOGE(TAG, "Failed to allocate endpoint recording buffer: %u bytes", (unsigned)max_bytes);
        return ESP_ERR_NO_MEM;
    }

    int16_t *frame = (int16_t *)heap_caps_malloc(frame_bytes, MALLOC_CAP_8BIT);
    if (frame == nullptr)
    {
        heap_caps_free(buffer);
        ESP_LOGE(TAG, "Failed to allocate endpoint frame buffer: %u bytes", (unsigned)frame_bytes);
        return ESP_ERR_NO_MEM;
    }

    uint8_t *preroll = nullptr;
    size_t preroll_frame_capacity = preroll_bytes / frame_bytes;
    if (preroll_frame_capacity > 0)
    {
        preroll = (uint8_t *)heap_caps_malloc(preroll_frame_capacity * frame_bytes, MALLOC_CAP_8BIT);
        if (preroll == nullptr)
        {
            heap_caps_free(frame);
            heap_caps_free(buffer);
            ESP_LOGE(TAG, "Failed to allocate preroll buffer: %u bytes", (unsigned)(preroll_frame_capacity * frame_bytes));
            return ESP_ERR_NO_MEM;
        }
    }

    const uint32_t frame_ms = frame_duration_ms(frame_bytes);
    const uint32_t start_confirm_ms = AI_RECORD_START_CONFIRM_MS;
    const size_t sample_count_per_frame = frame_bytes / BYTES_PER_SAMPLE;
    size_t recorded_bytes = 0;
    size_t preroll_next_frame = 0;
    size_t preroll_frame_count = 0;
    uint32_t elapsed_ms = 0;
    uint32_t recording_ms = 0;
    uint32_t speech_ms = 0;
    uint32_t silence_ms = 0;
    uint32_t max_rms = 0;
    uint32_t max_peak = 0;
    uint32_t noise_floor = AI_RECORD_STOP_RMS_THRESHOLD;
    bool recording_started = false;
    const char *finish_reason = "max_duration";

    uint32_t noise_sample_ms = 0;
    uint32_t noise_frame_count = 0;
    uint64_t noise_sum = 0;
    uint32_t noise_min = UINT32_MAX;

    ESP_LOGI(TAG,
             "Endpoint recorder calibrating noise: sample=%d ms, timeout=%u ms, max=%d ms, min=%d ms, silence_end=%d ms, frame=%u ms",
             AI_RECORD_NOISE_SAMPLE_MS,
             (unsigned)start_timeout_ms,
             AI_RECORD_MAX_DURATION_MS,
             AI_RECORD_MIN_DURATION_MS,
             AI_RECORD_SILENCE_END_MS,
             (unsigned)frame_ms);

    while (noise_sample_ms < AI_RECORD_NOISE_SAMPLE_MS)
    {
        esp_err_t ret = bsp_get_feed_data(false, frame, frame_bytes);
        if (ret != ESP_OK)
        {
            heap_caps_free(preroll);
            heap_caps_free(frame);
            heap_caps_free(buffer);
            ESP_LOGE(TAG, "Failed to read microphone frame during noise calibration: %s", esp_err_to_name(ret));
            return ret;
        }

        apply_recording_gain(frame, sample_count_per_frame);
        frame_audio_stats_t stats = calculate_frame_stats(frame, sample_count_per_frame);
        noise_sum += stats.rms;
        noise_frame_count++;
        if (stats.rms < noise_min)
        {
            noise_min = stats.rms;
        }
        if (stats.rms > max_rms)
        {
            max_rms = stats.rms;
        }
        if (stats.peak > max_peak)
        {
            max_peak = stats.peak;
        }

        if (preroll_frame_capacity > 0)
        {
            memcpy(preroll + preroll_next_frame * frame_bytes, frame, frame_bytes);
            preroll_next_frame = (preroll_next_frame + 1) % preroll_frame_capacity;
            if (preroll_frame_count < preroll_frame_capacity)
            {
                preroll_frame_count++;
            }
        }

        noise_sample_ms += frame_ms;
    }

    if (noise_frame_count > 0)
    {
        uint32_t noise_avg = (uint32_t)(noise_sum / noise_frame_count);
        uint32_t min_limited = noise_min == UINT32_MAX ? noise_avg : noise_min * 2 + AI_RECORD_STOP_NOISE_MARGIN;
        noise_floor = noise_avg < min_limited ? noise_avg : min_limited;
    }

    ESP_LOGI(TAG,
             "Endpoint recorder waiting for speech: noise_floor=%u, start_threshold=%u, stop_threshold=%u",
             (unsigned)noise_floor,
             (unsigned)dynamic_start_threshold(noise_floor),
             (unsigned)dynamic_stop_threshold(noise_floor));

    while (elapsed_ms < start_timeout_ms || recording_started)
    {
        esp_err_t ret = bsp_get_feed_data(false, frame, frame_bytes);
        if (ret != ESP_OK)
        {
            heap_caps_free(preroll);
            heap_caps_free(frame);
            heap_caps_free(buffer);
            ESP_LOGE(TAG, "Failed to read microphone frame: %s", esp_err_to_name(ret));
            return ret;
        }

        apply_recording_gain(frame, sample_count_per_frame);
        frame_audio_stats_t stats = calculate_frame_stats(frame, sample_count_per_frame);
        if (stats.rms > max_rms)
        {
            max_rms = stats.rms;
        }
        if (stats.peak > max_peak)
        {
            max_peak = stats.peak;
        }

        if (!recording_started)
        {
            uint32_t start_threshold = dynamic_start_threshold(noise_floor);
            if (preroll_frame_capacity > 0)
            {
                memcpy(preroll + preroll_next_frame * frame_bytes, frame, frame_bytes);
                preroll_next_frame = (preroll_next_frame + 1) % preroll_frame_capacity;
                if (preroll_frame_count < preroll_frame_capacity)
                {
                    preroll_frame_count++;
                }
            }

            if (stats.rms >= start_threshold)
            {
                speech_ms += frame_ms;
            }
            else
            {
                speech_ms = 0;
                noise_floor = (noise_floor * 7 + stats.rms) / 8;
            }

            if (speech_ms >= start_confirm_ms)
            {
                recording_started = true;
                size_t oldest_frame = preroll_frame_count == preroll_frame_capacity ? preroll_next_frame : 0;
                for (size_t i = 0; i < preroll_frame_count; i++)
                {
                    size_t frame_index = (oldest_frame + i) % preroll_frame_capacity;
                    if (!append_audio_frame((uint8_t *)buffer, max_bytes, &recorded_bytes, preroll + frame_index * frame_bytes, frame_bytes))
                    {
                        finish_reason = "buffer_full";
                        break;
                    }
                }
                recording_ms = (uint32_t)((recorded_bytes * 1000) / (SAMPLE_RATE_HZ * BYTES_PER_SAMPLE));
                silence_ms = 0;
                ESP_LOGI(TAG, "Speech detected: rms=%u, peak=%u, noise_floor=%u, start_threshold=%u, preroll=%u bytes",
                         (unsigned)stats.rms,
                         (unsigned)stats.peak,
                         (unsigned)noise_floor,
                         (unsigned)start_threshold,
                         (unsigned)recorded_bytes);
            }

            elapsed_ms += frame_ms;
            continue;
        }

        if (!append_audio_frame((uint8_t *)buffer, max_bytes, &recorded_bytes, (const uint8_t *)frame, frame_bytes))
        {
            finish_reason = "buffer_full";
            break;
        }
        recording_ms = (uint32_t)((recorded_bytes * 1000) / (SAMPLE_RATE_HZ * BYTES_PER_SAMPLE));

        uint32_t stop_threshold = dynamic_stop_threshold(noise_floor);
        if (stats.rms <= stop_threshold)
        {
            silence_ms += frame_ms;
        }
        else
        {
            silence_ms = 0;
        }

        if (recorded_bytes >= max_bytes)
        {
            finish_reason = "max_duration";
            break;
        }
        if (recorded_bytes >= min_bytes && silence_ms >= AI_RECORD_SILENCE_END_MS)
        {
            finish_reason = "silence_end";
            break;
        }
    }

    heap_caps_free(preroll);
    heap_caps_free(frame);

    if (!recording_started || recorded_bytes == 0)
    {
        heap_caps_free(buffer);
        ESP_LOGW(TAG, "Endpoint recorder timed out before speech: waited=%u ms, max_rms=%u, max_peak=%u",
                 (unsigned)elapsed_ms, (unsigned)max_rms, (unsigned)max_peak);
        return ESP_ERR_TIMEOUT;
    }

    recording->samples = buffer;
    recording->byte_len = recorded_bytes;
    recording->sample_rate = SAMPLE_RATE_HZ;
    recording->duration_ms = recording_ms;
    ESP_LOGI(TAG, "Endpoint recorder finished: %u bytes, %u ms, reason=%s, max_rms=%u, max_peak=%u, gain=%d",
             (unsigned)recorded_bytes,
             (unsigned)recording_ms,
             finish_reason,
             (unsigned)max_rms,
             (unsigned)max_peak,
             AI_RECORD_GAIN);
    return ESP_OK;
}

void audio_recorder_free(audio_recording_t *recording)
{
    if (recording == nullptr)
    {
        return;
    }
    if (recording->samples != nullptr)
    {
        heap_caps_free(recording->samples);
    }
    memset(recording, 0, sizeof(*recording));
}

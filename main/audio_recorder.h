#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct
{
    int16_t *samples;
    size_t byte_len;
    uint32_t sample_rate;
    uint32_t duration_ms;
} audio_recording_t;

esp_err_t audio_recorder_record_pcm(audio_recording_t *recording, uint32_t duration_ms, int frame_bytes);
esp_err_t audio_recorder_record_pcm_endpoint(audio_recording_t *recording, int frame_bytes, uint32_t start_timeout_ms);
void audio_recorder_free(audio_recording_t *recording);

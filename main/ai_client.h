#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "voice_trace.h"

typedef struct
{
    char reply_text[256];
    char recognized_text[256];
    char asr_status[32];
    char asr_backend[32];
    char motion[32];
    char audio_url[160];
    int asr_ms;
    int dialogue_ms;
    int tts_ms;
    int total_pipeline_ms;
    int body_receive_ms;
    int prepare_audio_ms;
    int total_request_ms;
} ai_response_t;

esp_err_t ai_client_send_pcm(const int16_t *samples, size_t byte_len, uint32_t sample_rate, ai_response_t *response,
                             voice_trace_t *trace = nullptr);

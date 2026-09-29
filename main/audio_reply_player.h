#pragma once

#include "esp_err.h"
#include "voice_trace.h"

typedef void (*audio_reply_start_callback_t)(void *context);
esp_err_t audio_reply_play_from_url(const char *audio_url, voice_trace_t *trace = nullptr,
                                    audio_reply_start_callback_t on_start = nullptr, void *context = nullptr);
esp_err_t audio_reply_download_only(const char *audio_url, voice_trace_t *trace);

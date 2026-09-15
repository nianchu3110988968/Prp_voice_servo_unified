#pragma once

#include "esp_err.h"
#include "voice_trace.h"

esp_err_t audio_reply_play_from_url(const char *audio_url, voice_trace_t *trace = nullptr);

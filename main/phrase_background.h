#pragma once
#include "ai_client.h"

// Reserve before advertising capability. At most two outstanding background
// downloads; a saturated device uses the compatible ordinary response path.
bool phrase_background_reserve();
void phrase_background_release();
esp_err_t phrase_background_collect(const char *job_url, const voice_trace_t *trace, ai_response_t *result);
void phrase_background_start(const char *job_url, const voice_trace_t *trace);

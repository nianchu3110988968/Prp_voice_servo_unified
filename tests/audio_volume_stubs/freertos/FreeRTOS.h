#pragma once
#include <stdint.h>
#include <mutex>
typedef std::mutex portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED {}
#define portENTER_CRITICAL(muxPtr) ((muxPtr)->lock())
#define portEXIT_CRITICAL(muxPtr) ((muxPtr)->unlock())
#define pdMS_TO_TICKS(ms) (ms)
#define portMAX_DELAY UINT32_MAX

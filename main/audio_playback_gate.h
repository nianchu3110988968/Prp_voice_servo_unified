#pragma once

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

// One owner across welcome prompts, replies and explicit stop. Fail rather
// than queue an audio/action pair behind unrelated playback.
class AudioPlaybackGuard {
public:
    AudioPlaybackGuard() {
        portENTER_CRITICAL(&mux_);
        acquired_ = !busy_;
        if (acquired_) busy_ = true;
        portEXIT_CRITICAL(&mux_);
    }
    ~AudioPlaybackGuard() {
        if (!acquired_) return;
        portENTER_CRITICAL(&mux_);
        busy_ = false;
        portEXIT_CRITICAL(&mux_);
    }
    bool acquired() const { return acquired_; }
    AudioPlaybackGuard(const AudioPlaybackGuard &) = delete;
    AudioPlaybackGuard &operator=(const AudioPlaybackGuard &) = delete;
private:
    inline static portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
    inline static bool busy_ = false;
    bool acquired_ = false;
};

// Shared by the real BSP and host regression: the callback runs only after
// ownership, validation and amplifier warm-up, immediately before I2S write.
template <typename Prepare, typename Write>
esp_err_t audio_playback_run(Prepare prepare, Write write,
                            void (*on_start)(void *), void *context) {
    AudioPlaybackGuard guard;
    if (!guard.acquired()) return ESP_ERR_INVALID_STATE;
    esp_err_t ret = prepare();
    if (ret != ESP_OK) return ret;
    if (on_start) on_start(context); // Must be nonblocking; never runs in an ISR.
    return write();
}

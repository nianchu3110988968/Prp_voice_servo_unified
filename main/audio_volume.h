#pragma once

#include <stddef.h>
#include <stdint.h>
#include <atomic>
#include "esp_err.h"

// Playback-only state. Atomic access never holds a lock while I2S blocks.
// No persistence: every boot starts at the original amplitude.
class AudioVolume {
public:
    bool set(int percent) {
        if (percent < 0 || percent > 100) return false;
        percent_.store(percent, std::memory_order_relaxed);
        return true;
    }
    int get() const { return percent_.load(std::memory_order_relaxed); }
private:
    std::atomic<int> percent_{100};
};

// Byte-wise little-endian access supports immutable and unaligned PCM16.
// The product fits int32_t even at -32768 * 100. Division truncates toward zero.
template <typename Volume, typename Writer>
esp_err_t pcm16_write_attenuated(const uint8_t *source, size_t length,
                               Volume volume, Writer writer) {
    if (!source || !length || length % 2) return ESP_ERR_INVALID_ARG;
    uint8_t chunk[480]; // 240 samples / 15 ms at 16 kHz; bounded task stack.
    for (size_t offset = 0; offset < length;) {
        const size_t count = length - offset < sizeof(chunk) ? length - offset : sizeof(chunk);
        const int percent = volume(); // one coefficient per block, including partial writes
        if (percent < 0 || percent > 100) return ESP_ERR_INVALID_ARG;
        for (size_t i = 0; i < count; i += 2) {
            const uint32_t raw = uint32_t(source[offset + i]) | (uint32_t(source[offset + i + 1]) << 8);
            const int32_t sample = raw >= 0x8000U ? int32_t(raw) - 65536 : int32_t(raw);
            const int32_t scaled = sample * percent / 100;
            const uint16_t encoded = static_cast<uint16_t>(scaled);
            chunk[i] = static_cast<uint8_t>(encoded);
            chunk[i + 1] = static_cast<uint8_t>(encoded >> 8);
        }
        size_t sent = 0;
        while (sent < count) {
            size_t written = 0;
            const esp_err_t ret = writer(chunk + sent, count - sent, &written);
            // On failure, never retry a prefix which the device may have queued.
            if (ret != ESP_OK) return ret;
            if (!written || written > count - sent) return ESP_FAIL;
            sent += written; // even odd-byte partial writes resume at the exact byte
        }
        offset += count;
    }
    return ESP_OK;
}

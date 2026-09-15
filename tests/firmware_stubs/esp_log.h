#pragma once
// Host-only log sink; production still uses the real ESP-IDF logger.
inline void test_log(const char *, const char *, ...) {}
#define ESP_LOGI(...) test_log(__VA_ARGS__)

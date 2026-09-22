// Exercise the production GET/download-only branch. No network or audio device.
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <vector>
#include <string>
static size_t strlcpy(char *dst, const char *src, size_t n)
{
    size_t length = strlen(src);
    if (n) { size_t copy = length < n - 1 ? length : n - 1; memcpy(dst, src, copy); dst[copy] = 0; }
    return length;
}
static size_t strlcat(char *dst, const char *src, size_t n)
{
    size_t length = strlen(dst);
    return length + strlcpy(dst + length, src, n - length);
}
#include "../../main/audio_reply_player.cc"

static int allocations = 0, plays = 0, network_calls = 0;
static int http_status = 200;
static esp_err_t transport_result = ESP_OK;
static std::vector<uint8_t> payload;
static std::vector<std::string> events;
void test_log(const char *tag, const char *format, ...)
{
    fprintf(stderr, "[host:%s] ", tag);
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
}
void *heap_caps_malloc(size_t n, unsigned) { ++allocations; return malloc(n); }
void heap_caps_free(void *p) { if (p) --allocations; free(p); }
extern "C" esp_err_t bsp_play_audio(const uint8_t *, size_t n) { ++plays; assert(n == 4); return ESP_OK; }
void voice_trace_mark(voice_trace_t *, const char *event, int64_t *slot)
{
    events.emplace_back(event); *slot = (int64_t)events.size() * 1000;
}
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *c) { return new esp_http_client_config_t(*c); }
esp_err_t esp_http_client_set_header(esp_http_client_handle_t, const char *, const char *) { return ESP_OK; }
esp_err_t esp_http_client_perform(esp_http_client_handle_t client)
{
    ++network_calls;
    // Simulate an SDK that ignores a callback error: explicit overflow must fail.
    for (size_t i = 0; i < payload.size(); i += 1024)
    {
        int n = (int)((payload.size() - i) < 1024 ? payload.size() - i : 1024);
        esp_http_client_event_t event = {HTTP_EVENT_ON_DATA, client->user_data, n, payload.data() + i, nullptr, nullptr};
        client->event_handler(&event);
    }
    return transport_result;
}
int esp_http_client_get_status_code(esp_http_client_handle_t) { return http_status; }
esp_err_t esp_http_client_cleanup(esp_http_client_handle_t client) { delete client; return ESP_OK; }

static void check_url_construction()
{
    // Built with /GF-: do not hide cross-literal pointer subtraction by pooling.
    std::string origin = AI_SERVER_URL;
    size_t host = origin.find("://");
    assert(host != std::string::npos);
    size_t path = origin.find('/', host + 3);
    if (path != std::string::npos) origin.resize(path);
    const std::string expected = origin + "/recordings/test.wav";
    char url[256] = {};
    assert(build_absolute_url("/recordings/test.wav", url, sizeof(url)));
    assert(url == expected);
    assert(build_absolute_url("recordings/test.wav", url, sizeof(url)));
    assert(url == expected);
    std::vector<char> exact(expected.size() + 1);
    assert(build_absolute_url("recordings/test.wav", exact.data(), exact.size()));
    assert(std::string(exact.data()) == expected);
    assert(!build_absolute_url("recordings/test.wav", exact.data(), exact.size() - 1));
    assert(build_absolute_url("http://example.invalid/a.wav", url, sizeof(url)));
    assert(strcmp(url, "http://example.invalid/a.wav") == 0);
    assert(build_absolute_url("https://example.invalid/a.wav", url, sizeof(url)));
    assert(strcmp(url, "https://example.invalid/a.wav") == 0);
    char small[4] = {'x', 'x', 'x', '\0'};
    assert(!build_absolute_url("https://example.invalid/a.wav", small, sizeof(small)));
    assert(strcmp(small, "xxx") == 0);
    assert(!build_absolute_url(nullptr, url, sizeof(url)));
    assert(!build_absolute_url("", url, sizeof(url)));
    assert(!build_absolute_url("/a.wav", nullptr, 256));
    assert(!build_absolute_url("/a.wav", url, 0));
    puts("[host] URL construction checks: PASS (unpooled literals, relative/absolute URLs, exact bounds)");
}

int main()
{
    check_url_construction();
    voice_trace_t trace = {};
    payload.resize(48, 0);
    memcpy(payload.data(), "RIFF", 4); memcpy(payload.data() + 8, "WAVE", 4);
    memcpy(payload.data() + 12, "fmt ", 4); payload[16] = 16;
    memcpy(payload.data() + 36, "data", 4); payload[40] = 4; payload[44] = 1;
    esp_err_t first = audio_reply_download_only("/recordings/test.wav", &trace);
    fprintf(stderr, "[host] first download ret=%d, HTTP=%d, perform_calls=%d, bytes=%zu, trace_events=%zu\n",
            first, http_status, network_calls, payload.size(), events.size());
    assert(first == ESP_OK);
    assert(plays == 0 && allocations == 0 && network_calls == 1);
    assert((events == std::vector<std::string>{"download_start", "download_end"}));
    events.clear();
    assert(audio_reply_play_from_url("/recordings/test.wav", &trace) == ESP_OK);
    assert(plays == 1 && allocations == 0 && network_calls == 2);
    assert((events == std::vector<std::string>{"download_start", "download_end", "playback_start", "playback_end"}));
    puts("[host] Begin expected failure cases: HTTP 404, timeout, oversized and empty responses.");
    http_status = 404;
    assert(audio_reply_download_only("/missing.wav", &trace) != ESP_OK);
    http_status = 200;
    transport_result = ESP_ERR_TIMEOUT;
    assert(audio_reply_download_only("/slow.wav", &trace) != ESP_OK);
    transport_result = ESP_OK;
    payload.resize(512 * 1024 + 1);
    assert(audio_reply_download_only("/large.wav", &trace) != ESP_OK);
    assert(audio_reply_play_from_url("/large.wav", &trace) != ESP_OK);
    payload.clear();
    assert(audio_reply_download_only("/empty.wav", &trace) != ESP_OK);
    assert(plays == 1 && allocations == 0);
    puts("audio download host tests: PASS (URL construction, real GET, no playback/allocation, failures, normal playback)");
}

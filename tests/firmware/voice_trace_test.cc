// Compile production observer with fake clock/transport, not a reimplementation.
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <string>
#include <vector>
#include "../../main/voice_trace.cc"

static std::vector<std::string> log_lines;
void test_log(const char *, const char *format, ...)
{
    char line[2048];
    va_list args;
    va_start(args, format);
    vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    log_lines.emplace_back(line);
}
static bool logged(const char *text)
{
    for (const auto &line : log_lines)
        if (line.find(text) != std::string::npos) return true;
    return false;
}

static int64_t clock_us = 1000;
static TaskHandle_t task = (void *)1;
static int next_write = 0;
static int write_calls = 0;
static const char payload[] = "test";
int64_t esp_timer_get_time() { return clock_us += 100; }
uint32_t esp_random() { return 1234; }
TaskHandle_t xTaskGetCurrentTaskHandle() { return task; }
extern "C" int __real_esp_transport_write(esp_transport_handle_t t, const char *buffer, int len, int timeout)
{
    assert(t == (void *)9 && buffer == payload && len == 100 && timeout == 20000);
    ++write_calls;
    return next_write;
}
static int write_result(int result)
{
    next_write = result;
    int previous = write_calls;
    size_t logs_before = log_lines.size();
    int actual = __wrap_esp_transport_write((void *)9, payload, 100, 20000);
    assert(actual == result && write_calls == previous + 1);
    assert(log_lines.size() == logs_before); // Never print from transport writes.
    return actual;
}
int main()
{
    voice_trace_t trace, other;
    voice_trace_init(&trace);
    voice_trace_init(&other);
    assert(elapsed_ms(-1, 200) == -1 && elapsed_ms(500, 400) == -1);
    assert(elapsed_ms(1000, 5000) == 4);
    write_result(-1); // Unobserved writes, including errors, pass through unchanged.
    assert(!voice_trace_watch_upload(nullptr, 100));
    assert(voice_trace_watch_upload(&trace, 100));
    assert(!voice_trace_watch_upload(&other, 100));
    write_result(100); // HTTP headers must not be counted as PCM.
    assert(trace.upload_bytes == 0 && trace.upload_start_us == -1);
    voice_trace_upload_headers_sent(&trace);
    task = (void *)2;
    write_result(100); // Other tasks cannot contaminate this request.
    voice_trace_upload_headers_sent(&trace);
    voice_trace_unwatch_upload(&trace);
    task = (void *)1;
    assert(trace.upload_attempts == 1 && trace.upload_bytes == 0);
    write_result(40);
    int64_t first = trace.upload_start_us;
    assert(first >= 0 && trace.upload_bytes == 40 && trace.upload_end_us == -1);
    write_result(0);
    write_result(-1);
    assert(trace.upload_bytes == 40 && trace.upload_end_us == -1);
    write_result(60);
    assert(trace.upload_bytes == 100 && trace.upload_end_us > first);
    write_result(100); // No response/other writes counted after completed body.
    assert(trace.upload_bytes == 100);
    voice_trace_upload_headers_sent(&trace); // Last attempt after redirect/auth retry.
    assert(trace.upload_attempts == 2 && trace.upload_bytes == 0 && trace.upload_end_us == -1);
    write_result(100);
    assert(trace.upload_bytes == 100 && trace.upload_start_us > first);
    voice_trace_unwatch_upload(&trace);
    write_result(50);
    assert(trace.upload_bytes == 100);
    assert(voice_trace_watch_upload(&other, 100));
    voice_trace_upload_headers_sent(&other);
    write_result(-1); // Failed body retains missing end, never zero-duration success.
    assert(other.upload_start_us >= 0 && other.upload_end_us == -1 && other.upload_bytes == 0);
    voice_trace_unwatch_upload(&other);
    voice_trace_t demo;
    voice_trace_init(&demo);
    log_lines.clear();
    demo.started_us = 100000;
    demo.recording_end_us = 300000;
    demo.request_start_us = 320000;
    demo.upload_start_us = 340000;
    demo.upload_end_us = 360000;
    demo.request_end_us = 900000;
    demo.json_received_us = 880000;
    demo.download_start_us = 920000;
    demo.download_end_us = 970000;
    demo.playback_start_us = 980000;
    demo.playback_end_us = 1980000;
    voice_trace_event(&demo, "recording_end", demo.recording_end_us);
    voice_trace_event(&demo, "request_end", demo.request_end_us);
    voice_trace_event(&demo, "json_received", demo.json_received_us);
    voice_trace_event(&demo, "download_end", demo.download_end_us);
    voice_trace_event(&demo, "playback_start", demo.playback_start_us);
    voice_trace_event(&demo, "playback_end", demo.playback_end_us);
    voice_trace_finish(&demo, "ok");
    assert(log_lines.size() == 7);
    assert(logged("录音结束=200ms"));
    assert(logged("上传开始=240ms → 上传结束=260ms | 上传耗时=20ms | HTTP往返=580ms"));
    assert(logged("收到JSON=780ms | 录音结束至JSON=580ms"));
    assert(logged("下载开始=820ms → 下载结束=870ms | 下载耗时=50ms"));
    assert(logged("播放开始=880ms | 录音结束至播放=680ms"));
    assert(logged("播放结束=1880ms | 播放耗时=1000ms"));
    assert(logged("本轮结果=完成(ok) | 录音结束至播放结束=1680ms"));
    for (const auto &line : log_lines) assert(line.find(demo.request_id) != std::string::npos);
    assert(!logged("VOICE_"));
    voice_trace_t background = demo;
    background.background_download = true;
    background.download_start_us = 2100000;
    background.download_end_us = 2200000;
    voice_trace_event(&background, "download_end", background.download_end_us);
    assert(logged("后台（不播放）下载开始=2000ms"));
    assert(demo.download_end_us == 970000 && demo.playback_end_us == 1980000);
    demo.cached_playback = true;
    voice_trace_event(&demo, "playback_start", demo.playback_start_us);
    assert(logged("缓存播放开始=880ms"));
    log_lines.clear();
    voice_trace_init(&demo);
    voice_trace_finish(&demo, "no_speech");
    assert(logged("未检测到开口(no_speech)"));
    assert(logged("录音结束至播放结束=-1ms"));
    puts("voice_trace host tests: PASS (transport isolation/retry/passthrough/Chinese timing/failure logs)");
}

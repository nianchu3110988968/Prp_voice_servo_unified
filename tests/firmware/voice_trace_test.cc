// Compile production observer with fake clock/transport, not a reimplementation.
#include <assert.h>
#include <stdio.h>
#include "../../main/voice_trace.cc"

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
    int actual = __wrap_esp_transport_write((void *)9, payload, 100, 20000);
    assert(actual == result && write_calls == previous + 1);
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
    puts("voice_trace host tests: PASS (partial/error/task isolation/retry/passthrough)");
}

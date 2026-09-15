#pragma once

#include <stddef.h>
#include <stdint.h>

// Diagnostic only. -1 means not observed; never treat a failed stage as zero ms.
struct voice_trace_t
{
    char request_id[48];
    int64_t started_us;
    int64_t recording_end_us;
    int64_t request_start_us;
    int64_t request_end_us;
    int64_t upload_start_us;
    int64_t upload_end_us;
    int64_t json_received_us;
    int64_t download_start_us;
    int64_t download_end_us;
    int64_t playback_start_us;
    int64_t playback_end_us;
    size_t upload_bytes;
    unsigned upload_attempts;
};

void voice_trace_init(voice_trace_t *trace);
void voice_trace_event(const voice_trace_t *trace, const char *event, int64_t at_us);
void voice_trace_mark(voice_trace_t *trace, const char *event, int64_t *slot);
void voice_trace_finish(const voice_trace_t *trace, const char *result);
// Observe transport writes on the calling task, without changing perform/retries.
bool voice_trace_watch_upload(voice_trace_t *trace, size_t expected_bytes);
void voice_trace_upload_headers_sent(voice_trace_t *trace);
void voice_trace_unwatch_upload(voice_trace_t *trace);

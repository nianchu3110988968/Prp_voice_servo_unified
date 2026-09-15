#pragma once

// Edit these values before uploading the AI bridge firmware.
// Keep the computer and ESP32-S3 on the same Wi-Fi network.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define AI_SERVER_URL "http://192.168.1.100:8000/voice/interact"

// Leave enabled. If WIFI_SSID is empty, the bridge is skipped at runtime.
#define AI_BRIDGE_ENABLED 1
#define AI_RECORD_DURATION_MS 5000
#define AI_RECORD_GAIN 3

// Endpoint-based recording. Set to 0 to fall back to fixed-duration recording.
#define AI_RECORD_ENDPOINT_ENABLED 1
#define AI_RECORD_START_TIMEOUT_MS 3000
#define AI_CHAT_CONTINUE_ENABLED 1
#define AI_CHAT_MAX_FOLLOWUP_TURNS 8
// After each reply finishes, keep listening until 30 seconds of inactivity.
#define AI_CHAT_FOLLOWUP_TIMEOUT_MS 30000
#define AI_RECORD_MAX_DURATION_MS 9000
#define AI_RECORD_MIN_DURATION_MS 700
#define AI_RECORD_SILENCE_END_MS 1000
#define AI_RECORD_PREROLL_MS 300
#define AI_RECORD_START_CONFIRM_MS 80
#define AI_RECORD_NOISE_SAMPLE_MS 500
#define AI_RECORD_START_RMS_THRESHOLD 220
#define AI_RECORD_STOP_RMS_THRESHOLD 160
#define AI_RECORD_START_NOISE_MARGIN 180
#define AI_RECORD_STOP_NOISE_MARGIN 100
#define AI_RECORD_START_NOISE_MULTIPLIER_PERCENT 170
#define AI_RECORD_STOP_NOISE_MULTIPLIER_PERCENT 130

# AI Bridge 录音端点检测模块说明

本文记录 ESP32 端 AI bridge 录音逻辑的设计与维护约定。后续如果修改录音状态机、阈值、缓冲策略或上传行为，必须同步更新本文档。

## 目标

唤醒词触发后，不再固定录满 5 秒，而是根据用户真实说话区间录音：

```text
播放欢迎音 -> 等待用户开口 -> 检测到说话后正式录音 -> 连续静音后结束 -> 上传有效语音片段
```

预期收益：

- 短句减少等待时间。
- 长句可录到更长时间，避免 5 秒截断。
- 用户不开口时自动退出 AI bridge，回到本地命令词模式。
- 日志能显示录音时长、结束原因和音量指标，便于后续调参。
- 一次唤醒后可继续等待多句追问，不需要每句话都重新唤醒。

## 当前实现边界

- 端点检测只在 ESP32 端做轻量能量判断，不引入复杂 VAD 模型。
- 端点检测使用环境噪声基线和动态阈值，不再只依赖固定 RMS 阈值。
- 服务端协议不变，仍上传 `pcm_s16le_mono / 16000 Hz`。
- 原固定时长录音函数保留，便于通过配置回退。
- 大模型、ASR、TTS 均仍在电脑服务器侧处理。

## 配置项

配置位于：

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

核心配置：

```cpp
#define AI_RECORD_ENDPOINT_ENABLED 1
#define AI_RECORD_START_TIMEOUT_MS 3000
#define AI_CHAT_CONTINUE_ENABLED 1
#define AI_CHAT_MAX_FOLLOWUP_TURNS 8
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
```

含义：

- `AI_RECORD_ENDPOINT_ENABLED`：启用端点检测；设为 `0` 时回退到固定时长录音。
- `AI_RECORD_START_TIMEOUT_MS`：唤醒后等待用户开始说话的最长时间。
- `AI_CHAT_CONTINUE_ENABLED`：启用连续对话；第一次回复播放后继续等待用户下一句话。
- `AI_CHAT_MAX_FOLLOWUP_TURNS`：一次唤醒后最多继续听几轮后续发言；当前为 8 轮，防止会话无限占用设备。
- `AI_CHAT_FOLLOWUP_TIMEOUT_MS`：每次回复播放结束后等待下一句话的无操作超时；当前为 30 秒。30 秒内检测到语音会继续本次会话，超时才返回唤醒词模式。
- `AI_RECORD_MAX_DURATION_MS`：正式录音最长时间。
- `AI_RECORD_MIN_DURATION_MS`：正式录音最短时间，避免刚开口就被静音截断。
- `AI_RECORD_SILENCE_END_MS`：正式录音后，连续静音达到该时长则结束。
- `AI_RECORD_PREROLL_MS`：检测到开口时，向前保留的短音频，避免丢掉句首。
- `AI_RECORD_START_CONFIRM_MS`：开始阈值需要连续满足的时间，降低噪声误触发。
- `AI_RECORD_NOISE_SAMPLE_MS`：正式等待开口前，用于估计环境噪声底的采样时间。
- `AI_RECORD_START_RMS_THRESHOLD`：开始说话的最低 RMS 阈值。
- `AI_RECORD_STOP_RMS_THRESHOLD`：静音结束的最低 RMS 阈值。
- `AI_RECORD_START_NOISE_MARGIN` / `AI_RECORD_STOP_NOISE_MARGIN`：基于环境噪声底增加的阈值余量。
- `AI_RECORD_START_NOISE_MULTIPLIER_PERCENT` / `AI_RECORD_STOP_NOISE_MULTIPLIER_PERCENT`：基于环境噪声底放大的动态阈值比例。

## 状态机

端点检测录音使用两个状态：

```text
WAITING_FOR_SPEECH
  - 先采样一小段环境音，估计 noise_floor。
  - 持续读取麦克风帧并写入 pre-roll 环形缓冲。
  - RMS 连续超过动态开始阈值达到确认时间后进入 RECORDING。
  - 超过等待开口时间仍未检测到说话，则返回超时错误。

RECORDING
  - 继续读取并写入主录音缓冲。
  - 达到最短录音时间后，如果连续低于动态停止阈值超过结束时间，则结束。
  - 达到最长录音时间后强制结束。
```

进入 `RECORDING` 时，会先把 pre-roll 缓冲按时间顺序写入主录音缓冲，再继续追加后续音频。

## 日志

2026-09-15日志增强：`2026-09-15-latency-v1`在录音调用前后增加同请求ID的`recording_start/recording_end`，并关联上传、JSON、下载、播放和服务器耗时；未改本文件中的端点参数/录音状态机。`recording_end`是函数返回时刻，不等同用户最后音节结束，端点静音等待仍在录音阶段内。具体定义见 `E:\Projects2026\Prp_voice_servo_unified\docs\项目指南\voice_latency_logging.md`。本版需编译验证后由用户另行确认烧录，不能把代码事件当作已经取得的硬件数据。

串口日志应能看到：

```text
Endpoint recorder calibrating noise: sample=500 ms, timeout=...
AI bridge recording started: endpoint=1, fixed_duration=5000 ms
Endpoint recorder waiting for speech: noise_floor=..., start_threshold=..., stop_threshold=...
Speech detected: rms=..., peak=..., noise_floor=..., start_threshold=..., preroll=... bytes
Endpoint recorder finished: ... ms, ... bytes, reason=silence_end/max_duration
AI bridge follow-up listening: turn=1/8, timeout=30000 ms
```

如果欢迎音播放后直接出现：

```text
进入命令词识别模式，请说出指令...
```

且没有看到 `AI bridge recording started` 或 `Endpoint recorder waiting for speech`，说明程序没有进入端点检测录音。优先检查：

- `status ai bridge` 中 `AI bridge ready` 是否为 `1`。
- `Wi-Fi status` 是否为 `connected`。
- `AI_SERVER_URL` 是否指向当前电脑 IP。
- 必要时在串口输入 `retry wifi` 后再次测试。

服务端日志应能看到：

```text
[ai_bridge] received ... bytes
[ai_bridge] recognized='...', ... llm=ok/ollama, tts=ok/windows_sapi
```

## 调参建议

如果经常没开始录音：

- 降低 `AI_RECORD_START_RMS_THRESHOLD`。
- 增大 `AI_RECORD_START_TIMEOUT_MS`。

如果环境噪声触发录音：

- 提高 `AI_RECORD_START_RMS_THRESHOLD`。
- 增大 `AI_RECORD_START_CONFIRM_MS`。

如果句尾被截断：

- 增大 `AI_RECORD_SILENCE_END_MS`。
- 降低 `AI_RECORD_STOP_RMS_THRESHOLD`。

如果结束太慢：

- 降低 `AI_RECORD_SILENCE_END_MS`。
- 提高 `AI_RECORD_STOP_RMS_THRESHOLD`。

## 验证方式

编译验证：

```powershell
platformio run
```

烧录后串口测试：

```powershell
pio device monitor -p COM7 -b 115200
```

串口中可先输入：

```text
status ai bridge
```

确认：

```text
AI bridge enabled: 1
Wi-Fi status: connected
AI bridge ready: 1
```

电脑服务器日志：

```powershell
Get-Content E:\Projects2026\Prp_voice_servo_unified\server\uvicorn.out.log -Wait -Encoding UTF8
```

测试短句：

```text
我今天压力好大，请安慰我一下
```

预期表现：

- ESP32 不再固定等待 5 秒。
- 服务端收到的 PCM 字节数随实际说话长短变化。
- `llm=ok/ollama`，`tts=ok/windows_sapi`。
- 第一次回复播放后，串口应进入 `AI bridge follow-up listening`，可直接继续说下一句话。

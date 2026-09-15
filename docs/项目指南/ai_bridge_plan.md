# AI 电脑服务器桥接方案

本文档记录“毛绒治愈机器人 PRP”项目的第一版联网语音桥接方案。后续方案说明和测试步骤默认使用中文维护。

## 一、目标

ESP32-S3 不直接承担大模型推理和高质量语音合成，而是作为本地感知与执行前端：

- 本地唤醒词检测；
- 麦克风录音；
- 扬声器播放；
- 舵机、触摸、震动、加热等身体反馈控制；
- 网络请求电脑服务器；
- 接收服务器返回的回复文本、动作意图和后续音频资源。

电脑服务器负责更重的 AI 能力：

- ASR：把用户语音转成文本；
- LLM：理解用户意图并生成治愈型回复；
- TTS：生成个性化、柔和音色的语音；
- 动作意图规划：告诉 ESP32 应该触发哪类身体反馈。

## 二、第一版最小链路

当前已实现的是“网络通路验证版”，还不是完整 AI 对话版。

流程如下：

1. ESP32-S3 启动后尝试连接 Wi-Fi。
2. 如果 Wi-Fi 配置为空或连接失败，则跳过 AI bridge，保留原来的本地语音命令测试模式。
3. 用户说出本地唤醒词后，ESP32 播放本地欢迎音频，作为“可以开始说话”的提示。
4. 欢迎音频播放结束后，ESP32 录制约 5 秒 PCM 音频，格式为 16 kHz、16 bit、mono。
5. ESP32 通过 HTTP POST 把原始 PCM 音频上传到电脑服务器。
6. 电脑服务器保存这段 PCM 文件，并返回一段测试 JSON。
7. ESP32 解析 JSON，打印回复文本，并根据 `motion` 字段触发已有动作函数。
8. 处理完成后返回等待唤醒状态。

## 三、当前 ESP32 配置文件

联网配置在：

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

需要关注的字段：

| 字段 | 作用 |
| --- | --- |
| `WIFI_SSID` | Wi-Fi 名称。 |
| `WIFI_PASSWORD` | Wi-Fi 密码。 |
| `AI_SERVER_URL` | 电脑服务器接口地址。 |
| `AI_BRIDGE_ENABLED` | 是否启用 AI bridge 逻辑。 |
| `AI_RECORD_DURATION_MS` | 欢迎音频播放结束后的录音时长，当前默认 5000 ms。 |

示例：

```cpp
#define WIFI_SSID "你的WiFi名称"
#define WIFI_PASSWORD "你的WiFi密码"
#define AI_SERVER_URL "http://192.168.1.23:8000/voice/interact"
```

注意：电脑和 ESP32-S3 必须连接到同一个局域网。

## 四、电脑测试服务器

测试服务器文件：

```text
E:\Projects2026\Prp_voice_servo_unified\server\ai_bridge_server.py
```

依赖文件：

```text
E:\Projects2026\Prp_voice_servo_unified\server\requirements.txt
```

服务器启动后，会提供两个接口：

| 接口 | 作用 |
| --- | --- |
| `GET /health` | 检查服务器是否正常运行。 |
| `POST /voice/interact` | 接收 ESP32 上传的 PCM 音频，并返回测试 JSON。 |

当前服务器会把收到的录音保存到：

```text
E:\Projects2026\Prp_voice_servo_unified\server\recordings
```

服务器会同时保存：

- `.pcm`：ESP32 上传的原始音频；
- `.wav`：自动转换后的可播放录音。

可以访问：

```text
http://127.0.0.1:8000/recordings
```

查看所有录音，再通过返回的 `url` 下载或播放对应 `.wav` 文件。

## 五、电脑服务器代码结构

| 文件 | 作用 |
| --- | --- |
| `server\ai_bridge_server.py` | FastAPI 主服务，负责接收音频、保存文件、返回结果。 |
| `server\services\asr_service.py` | ASR 占位层，后续接 Whisper、faster-whisper 或 SenseVoice。 |
| `server\services\dialogue_service.py` | 对话生成占位层，后续接本地/云端大模型。 |
| `server\services\tts_service.py` | TTS 占位层，后续接 CosyVoice、GPT-SoVITS、Fish Speech 或 Kokoro。 |
| `server\recordings` | 保存 ESP32 上传的录音。 |

## 六、服务器返回 JSON 约定

当前测试服务器返回：

```json
{
  "reply_text": "我收到你的声音了，下一步会在这里接入语音识别和治愈回复。",
  "motion": "comfort",
  "audio_url": "",
  "debug_recording": "recording_xxx_16000hz.pcm"
}
```

ESP32 当前会处理：

| 字段 | 当前用途 |
| --- | --- |
| `reply_text` | 在串口日志中打印，暂时不会被 ESP32 朗读。 |
| `motion` | 转换为本地动作函数。 |
| `audio_url` | 已预留，后续用于服务器返回动态语音地址。 |
| `debug_recording` | 服务器侧调试字段，ESP32 当前不依赖。 |

当前支持的动作意图：

| `motion` 值 | ESP32 动作 |
| --- | --- |
| `happy` | `robot_motions.actionHappy()` |
| `shy` | `robot_motions.actionShy()` |
| `comfort` | `robot_motions.actionCurious()` |
| `curious` | `robot_motions.actionCurious()` |
| `none` | 不触发动作 |

## 七、下一步开发方向

第一版只打通“录音上传 + JSON 返回 + 动作意图”的通路。后续建议按顺序继续：

1. 在电脑服务器中接入 ASR，把 PCM 转文字。
2. 接入大模型，根据用户文本生成治愈型回复。
3. 接入 TTS，生成柔和个性化音色。
4. 让服务器返回 16 kHz、16 bit、mono 的 PCM/WAV。
5. ESP32 下载或流式接收音频并通过 MAX98357A 播放。
6. 将服务器返回的动作、震动、加热意图统一接入机器人执行层。

## 八、当前 AI 服务层状态

当前已经搭建完成：

- ASR 服务层：默认占位，可切换为 `faster_whisper`；
- 对话生成层：默认规则兜底，可切换为本地 Ollama；
- TTS 服务层：当前占位，音效和个性化语音后续再接；
- 调试接口：`/config`、`/recordings`、`/debug/pipeline/{file_name}`。

当前服务器返回 JSON 会包含：

| 字段 | 作用 |
| --- | --- |
| `recognized_text` | ASR 识别文本。占位模式下为空。 |
| `asr_status` | ASR 状态，例如 `disabled`、`ok`、`missing_dependency`。 |
| `asr_backend` | 当前 ASR 后端。 |
| `asr_detail` | ASR 失败时的具体原因，便于排查模型下载或加载问题。 |
| `reply_text` | 生成的回复文本。 |
| `llm_status` | 回复生成状态，例如 `rule`、`ok`、`fallback_no_text`。 |
| `llm_backend` | 当前回复生成后端。 |
| `motion` | 返回给 ESP32 的动作意图。 |

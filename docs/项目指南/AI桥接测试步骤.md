# AI 电脑服务器桥接测试步骤

本文档用于手把手测试第一版 AI bridge：ESP32-S3 唤醒后录音，并把音频通过 Wi-Fi 发到电脑服务器。

## 一、测试前确认

你需要准备：

- ESP32-S3；
- INMP441 麦克风模块；
- MAX98357A 功放和扬声器；
- 电脑；
- 电脑和 ESP32-S3 能连接到同一个 Wi-Fi；
- 当前工程：`E:\Projects2026\Prp_voice_servo_unified`。

当前第一版只验证：

- ESP32 能连 Wi-Fi；
- ESP32 能访问电脑服务器；
- 唤醒后能录音；
- 电脑能收到并保存 PCM 音频；
- 电脑能返回 JSON；
- ESP32 能解析回复并触发动作意图。

当前第一版还没有完成：

- ASR 语音转文字；
- 大模型回复；
- 个性化 TTS；
- 服务器动态语音回传播放。

## 二、启动电脑测试服务器

打开一个新的 PowerShell 终端，执行：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python -m pip install -r requirements.txt
python -m uvicorn ai_bridge_server:app --host 0.0.0.0 --port 8000
```

如果启动成功，终端会显示类似：

```text
Uvicorn running on http://0.0.0.0:8000
```

这个终端不要关，它就是电脑服务器。

## 三、确认电脑服务器可访问

再打开一个 PowerShell 终端，执行：

```powershell
curl http://127.0.0.1:8000/health
```

如果正常，会返回类似：

```json
{"status":"ok"}
```

如果这一步失败，先不要烧录 ESP32，说明电脑服务器还没跑起来。

## 四、查看电脑局域网 IP

在 PowerShell 执行：

```powershell
ipconfig
```

找到当前正在使用的无线网卡，记录其中的 `IPv4 地址`。它通常长这样：

```text
192.168.1.23
```

注意不要用：

- `127.0.0.1`；
- `localhost`；
- 虚拟网卡 IP；
- 蓝牙网卡 IP。

ESP32 要访问的是电脑在局域网里的 IPv4 地址。

## 五、修改 ESP32 网络配置

打开：

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

把里面改成你的 Wi-Fi 和电脑 IP，例如：

```cpp
#define WIFI_SSID "你的WiFi名称"
#define WIFI_PASSWORD "你的WiFi密码"
#define AI_SERVER_URL "http://192.168.1.23:8000/voice/interact"
```

其中 `192.168.1.23` 要换成你自己电脑 `ipconfig` 看到的 IPv4 地址。

## 六、先编译，不急着上传

在 PowerShell 执行：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
platformio run
```

看到下面这行才表示编译成功：

```text
[SUCCESS]
```

`platformio run` 只编译，不会改 ESP32 板子里的固件。

## 七、确认后再上传固件

只有在你确认可以覆盖当前板子固件时，才执行：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
platformio run -t upload
```

如果上传失败，常见处理：

- 确认 ESP32 接的是能下载程序的 USB 口；
- 确认没有串口监视器占用 COM 口；
- 必要时按住 BOOT，再点一下 RESET，然后重新上传。

## 八、打开串口日志

上传完成后，打开串口监视器：

```powershell
pio device monitor -p COM7 -b 115200
```

如果你的端口不是 COM7，可以先查看设备：

```powershell
pio device list
```

在日志里重点看：

- 是否连接 Wi-Fi 成功；
- 是否打印 ESP32 获得的 IP；
- 是否进入等待唤醒状态；
- 唤醒后是否开始录音；
- 是否打印上传到 AI server；
- 是否打印服务器返回的 `reply_text` 和 `motion`。

## 九、实际语音测试

保持电脑服务器终端运行。

对着麦克风说唤醒词：

```text
你好小智
```

如果唤醒成功，ESP32 会：

1. 播放本地欢迎音频；
2. 欢迎音频播放结束后，录制约 5 秒声音；
3. 上传到电脑服务器；
4. 在串口里打印服务器返回内容；
5. 如果返回 `motion=comfort`，尝试触发 `actionCurious()`。

电脑服务器终端应该看到类似：

```text
[ai_bridge] received 96000 bytes, format=pcm_s16le_mono, sample_rate=16000, saved=recording_xxx_16000hz.pcm
```

如果看到这行，说明“ESP32 到电脑服务器”的核心链路已经通了。

## 十、查看录音文件

服务器保存的录音在：

```text
E:\Projects2026\Prp_voice_servo_unified\server\recordings
```

当前服务器会同时保存两种文件：

| 文件类型 | 用途 |
| --- | --- |
| `.pcm` | ESP32 上传的原始音频数据。 |
| `.wav` | 自动转换后的可播放音频，用于检查麦克风录音质量。 |

查看服务器收到的录音列表：

```powershell
curl http://127.0.0.1:8000/recordings
```

也可以在浏览器打开：

```text
http://127.0.0.1:8000/recordings
```

列表里会出现类似：

```json
{
  "name": "recording_20260830_171812_081721_16000hz.wav",
  "size": 95276,
  "url": "/recordings/recording_20260830_171812_081721_16000hz.wav"
}
```

要播放某条录音，把 `url` 拼到服务器地址后面，例如：

```text
http://127.0.0.1:8000/recordings/recording_20260830_171812_081721_16000hz.wav
```

如果你能听见刚才对 ESP32 说的话，说明麦克风录音、上传和服务器保存都正常。

## 十一、当前服务器代码结构

当前电脑服务器已经拆出 AI 服务框架：

| 文件 | 作用 |
| --- | --- |
| `server\ai_bridge_server.py` | FastAPI 主服务，负责接收音频、保存文件、返回结果。 |
| `server\services\asr_service.py` | ASR 占位层，后续接 Whisper、faster-whisper 或 SenseVoice。 |
| `server\services\dialogue_service.py` | 对话生成占位层，后续接本地/云端大模型。 |
| `server\services\tts_service.py` | TTS 占位层，后续接 CosyVoice、GPT-SoVITS、Fish Speech 或 Kokoro。 |
| `server\recordings` | 保存 ESP32 上传的录音。 |

现在 `/voice/interact` 已经按下面的顺序调用：

```text
保存 PCM
-> 转成 WAV
-> ASR 占位
-> 治愈回复生成占位
-> TTS 占位
-> 返回 JSON 给 ESP32
```

## 十二、常见问题

### 1. ESP32 日志提示 `WIFI_SSID is empty`

说明你还没有修改：

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

此时 AI bridge 会跳过，系统会继续使用本地命令词模式。

### 2. ESP32 连不上 Wi-Fi

检查：

- Wi-Fi 名称和密码是否正确；
- Wi-Fi 是否是 2.4 GHz；
- ESP32 和电脑是否在同一个网络；
- 手机热点是否开启了设备隔离。

如果串口输入 `retry wifi` 后显示：

```text
Wi-Fi retry result: ESP_ERR_NOT_FOUND
```

优先检查工程的 `partitions.csv` 是否包含 `nvs` 分区。ESP-IDF Wi-Fi 需要 NVS 分区才能启动。

### 3. 电脑服务器能本机访问，但 ESP32 访问失败

检查：

- `AI_SERVER_URL` 里不能写 `127.0.0.1`；
- 必须写电脑的局域网 IPv4；
- Windows 防火墙可能拦截了 8000 端口；
- 电脑和 ESP32 是否连在同一个路由器或热点下。

### 4. 电脑收不到录音

检查：

- 服务器终端是否还开着；
- 端口是否是 8000；
- `AI_SERVER_URL` 是否写成 `/voice/interact`；
- ESP32 串口日志是否显示 HTTP 请求失败。

### 5. 有动作日志但没接舵机

这是正常的。当前动作意图会调用已有动作函数，如果 PCA9685 没连接，动作模块可能跳过执行。单测语音桥接时可以先不接舵机。

## 十三、录音时机与音量调试

当前 AI bridge 模式下，唤醒词识别成功后会先播放本地欢迎音频。欢迎音频播放结束后，串口会打印 `AI bridge recording started`，此时开始录音；录音窗口默认持续 5 秒，结束后上传到电脑服务器处理。

如果 AI bridge 不可用，系统仍然回退到本地命令词模式。若 AI bridge 在录音或上传阶段失败，系统会进入本地命令词模式，方便继续验证离线命令词。

上传录音有独立数字增益，配置位置：

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

当前默认：

```cpp
#define AI_RECORD_DURATION_MS 5000
#define AI_RECORD_GAIN 3
```

如果录音仍然偏小，可以尝试改成 `4` 或 `5`；如果声音破音、爆音或噪声明显，则改回 `2` 或 `1`。

## 十四、整体 AI 链路调试

当前电脑服务器已经跑通下面这条结构：

```text
ESP32 上传 PCM
-> 服务器保存 PCM
-> 服务器转换 WAV
-> ASR 服务层
-> 治愈回复生成层
-> TTS 生成回复 WAV
-> ESP32 下载并播放回复音频
-> 返回 JSON 给 ESP32
```

当前为了保证链路稳定，ASR 默认还是占位模式。也就是说，服务器会明确返回：

```json
{
  "asr_status": "disabled",
  "asr_backend": "placeholder"
}
```

这不是错误，而是表示“语音转文字模型尚未启用”。

查看当前服务器配置：

```powershell
curl http://127.0.0.1:8000/config
```

用已有 WAV 录音跑一遍服务器 AI 管线：

```powershell
curl http://127.0.0.1:8000/debug/pipeline/你的录音文件名.wav
```

录音文件名可以从这里查看：

```powershell
curl http://127.0.0.1:8000/recordings
```

如果要启用本地 ASR，下一步计划使用 `faster-whisper`。操作思路是：

1. 安装 ASR 依赖：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python -m pip install -r requirements-asr.txt
```

2. 修改服务器配置：

```text
E:\Projects2026\Prp_voice_servo_unified\server\server_config.py
```

把：

```python
ASR_BACKEND = "placeholder"
```

改成：

```python
ASR_BACKEND = "faster_whisper"
```

3. 重启服务器。

第一次启用 `faster-whisper` 时，可能需要下载模型。当前默认模型是 `tiny`，优先用于跑通链路；后续如果识别准确率不够，再升级到 `base` 或 `small`。

## 十五、当前 ASR 状态

当前服务器已经安装 `faster-whisper`，并把 ASR 后端切换为：

```python
ASR_BACKEND = "faster_whisper"
```

配置位置：

```text
E:\Projects2026\Prp_voice_servo_unified\server\server_config.py
```

为了适配国内网络，服务器配置中已经加入：

```python
HF_ENDPOINT = "https://hf-mirror.com"
HF_HUB_DISABLE_XET = "1"
```

当前上传录音会做服务端音量归一化：

```python
AUDIO_NORMALIZE_TARGET_PEAK = 0.75
```

一次旧录音测试中，原始录音峰值只有约 2.5%，归一化后提升到约 75%。归一化后的旧录音可以被 ASR 识别，但只识别出“啊”，说明旧录音里的有效语音内容不足。下一步应使用已经提前录音、增加上传增益的新 ESP32 固件重新录制完整短句，再观察 `recognized_text`。

## 十六、语音回复链路测试

当前服务端已经接入 Windows SAPI 作为轻量 TTS 后端，用于优先测试“文字转音频 + ESP32 下载播放”的整体延迟。它不是最终音色方案，主要用于验证链路速度和稳定性。

完整流程：

```text
ESP32 唤醒
-> 播放本地欢迎音
-> 录音 5 秒
-> 上传 PCM 到电脑服务器
-> 服务端 ASR
-> 生成回复文本
-> 服务端生成 reply_xxx_16000hz.wav
-> 返回 audio_url 和 timings_ms
-> ESP32 下载 WAV
-> 跳过 WAV 头，播放 PCM 数据
```

服务端日志重点看：

```text
[ai_bridge] recognized='...'
tts=ok/windows_sapi
audio_url=/recordings/reply_xxx_16000hz.wav
timings_ms={...}
```

ESP32 串口日志重点看：

```text
AI bridge recording started
AI bridge recording finished
AI reply: recognized='...', ..., audio_url='/recordings/reply_xxx_16000hz.wav'
Downloading reply audio
Reply audio downloaded
Reply audio playback starting
Reply audio playback finished
```

本地测试某条录音是否能生成回复音频：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
$env:PYTHONIOENCODING='utf-8'; python server\tools\test_asr_file.py server\recordings\你的录音文件名.wav
```

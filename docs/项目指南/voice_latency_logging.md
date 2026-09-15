# 完整语音链路分段延迟日志

实现版本：`2026-09-15-latency-v1`。本轮仅增加观测，不调整录音阈值、连续对话轮数、超时、缓冲容量、上传/下载方式、动作顺序、音频播放方式或TTS后端。未烧录，硬件实测待用户确认后进行。串口日志本身存在少量开销，不能声称对运行时间完全没有影响。

## 请求关联与时钟

- 每轮有效进入录音流程时生成独立`esp-…`请求编号；续聊每轮有不同编号。
- ESP32通过`X-Request-ID`发送给`POST /voice/interact`，服务器在响应头原样回显合法编号。缺失或不合法编号由服务器生成，不破坏旧固件调用。
- ESP32的`VOICE_TRACE/VOICE_SUMMARY/VOICE_SERVER/VOICE_HTTP/VOICE_DOWNLOAD`均带`id`；服务器`[voice_trace]`后为JSON，带`request_id`。服务器`response_ready`关联本轮录音文件、回复音频URL与`timings_ms`。
- ESP使用`esp_timer_get_time()`微秒单调时钟；服务器使用`time.perf_counter()`。两个时钟没有同步，**只能通过编号关联，不能将两边绝对时间相减**。`logged_utc`是服务器实际打印时间，仅便于找日志。
- 某些事件在操作完成后延迟打印，分析时按事件内的`t_us/mono_us`排序，不以串口行顺序推断操作顺序。

## ESP32事件含义

| event | 计时边界 |
| --- | --- |
| recording_start | 进入录音流程，包括等待开口/噪声校准；不是检测到用户发声的时刻 |
| recording_end | 录音函数返回；包含端点静音判定，不等于最后一个字的声学结束时刻；失败也会返回此边界，须结合summary结果 |
| request_start / request_end | 原`esp_http_client_perform`调用前后，包含连接、上传、服务器处理和响应接收 |
| upload_start | HTTP头发送后，本轮请求体第一次transport write调用前 |
| upload_end | 成功写入累计PCM请求体字节数达到预期的最后一次transport write返回后；是本机网络栈接受请求体，不代表服务器已收到/确认所有字节 |
| json_received | HTTP完成回调时刻，在JSON解析成功后才输出这个事件 |
| json_parsed | JSON解析成功的时刻 |
| download_start / download_end | 回复音频GET的perform调用前后；end在失败时也记录，结合HTTP返回码判断 |
| playback_start / playback_end | 原`bsp_play_audio`调用前后；是软件API边界，不是用麦克风测出的扬声器首声/尾声 |

IDF 5.5只有`HEADERS_SENT`，没有`BODY_SENT`回调。`main/voice_trace.cc`使用链接器`--wrap=esp_transport_write`透明观测：只对绑定任务在HEADERS_SENT之后累计正数写入，参数原样转发一次，原返回值原样返回，不替换`esp_http_client_perform`或SDK文件，也不在写入钩子里打印日志。其他任务/下载不计入上传。重定向/认证重试保留最后一次尝试的时刻，`upload_attempts>1`单独分析；SDK升级必须重新验证链接与事件边界。

`VOICE_SUMMARY`中各值单位为毫秒：

- `record_call_ms`：录音流程耗时，包含等待开口。
- `request_ms`：完整HTTP请求耗时，不是纯上传耗时。
- `upload_ms`：请求体写入耗时，不含前面的DNS/连接/HTTP头。
- `download_ms`、`playback_call_ms`：下载和播放API耗时。
- `record_end_to_json_ms`、`record_end_to_play_start_ms`、`record_end_to_play_end_ms`：录音函数返回到JSON收到、播放调用开始和播放调用返回。
- 未到达的阶段使用`-1`而非0。`result`区分`ok/no_audio/no_speech/recording_failed/request_failed/audio_failed`，不把失败混入正常延迟样本。
- `VOICE_HTTP`记录返回码、HTTP状态、响应缓存是否截断；`VOICE_CORRELATION match=1`表示服务端回显编号匹配。旧服务器不回显或不提供新字段时，不阻止交互；新增服务器耗时字段显示`-1`。

## 服务端timings_ms

原有`asr/dialogue/tts/total_pipeline`含义保留；新增字段：

| 字段 | 含义 |
| --- | --- |
| body_receive | handler内等待`request.body()`；ASGI可能已缓存部分内容，不能当作完整上行网络时间 |
| prepare_audio | 读取音频头参数、统计/归一化、写PCM/WAV |
| asr | `transcribe_audio`调用时间，包含实际后端内部开销 |
| dialogue | 回复生成调用，包括规则/LLM回退；不是只计模型token生成 |
| tts | 整个`synthesize_reply`，包含TTS请求、WAV规范化及可能的SAPI回退 |
| total_pipeline | ASR＋回复＋TTS及流水线内部开销，不包含body_receive/prepare_audio |
| total_request | handler入口到回复字典准备完成，包含预处理与流水线；不含FastAPI JSON序列化、发送与ESP下载/播放 |

服务器同时输出body_receive、prepare_audio、asr、dialogue、tts的开始/结束事件；失败输出`request_failed`并保持原异常路径。`response_ready`不是“JSON已经传到设备”。阶段日志中的`status=ok`表示函数正常返回，实际是否走回退仍看原响应的`asr_status/llm_status/tts_status`。

不要将`request_ms-total_pipeline`命名为“网络延迟”，差值还含服务器预处理/调度、连接和响应开销。首声等待以`record_end_to_play_start_ms`作为软件近似值，正式声学延迟需额外测量。单次数据和模拟测试不构成论文P50/P90结论。

## 代码位置

工程根目录：`E:\Projects2026\Prp_voice_servo_unified`。

- `main\voice_trace.h/.cc`：请求编号、时刻、汇总、只观测的上传写入钩子。
- `main\CMakeLists.txt`：编译新模块、链接包装transport write。
- `main\main.cc::run_ai_bridge_interaction`：录音边界、响应耗时、整轮结果；固件版本号更新。
- `main\ai_client.h/.cc::ai_client_send_pcm`：请求头、HTTP/JSON边界和新timings字段。
- `main\audio_reply_player.h/.cc::audio_reply_play_from_url`：下载和播放边界，不改先完整下载再播放的行为。
- `server\services\latency_trace.py`：安全请求编号和结构化阶段日志。
- `server\ai_bridge_server.py::voice_interact/run_ai_pipeline`：保持业务结果，附加timings与请求关联。
- `server\tests\test_latency_trace.py`：离线协议/异常/时序测试，无真实模型调用。
- `tests\firmware\voice_trace_test.cc`与`tests\firmware_stubs`：编译真实上传观测代码做主机模拟；不代替ESP32网络与硬件测试。

## 验证与后续实测命令

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
python -X utf8 -m unittest discover -s server/tests -p test_latency_trace.py -v
platformio run
```

预期：服务端5项测试通过、固件构建SUCCESS。没有upload参数，不会烧录。

以下仅为获得烧录确认并完成烧录后的串口采集步骤，本轮不要直接烧录：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
pio device monitor --port COM7 --baud 115200 --filter log2file
```

预期固件版本`2026-09-15-latency-v1`；首轮及连续问答每轮一个新ID，有完整VOICE_TRACE与VOICE_SUMMARY。日志保存在启动目录的`device-monitor-*.log`（以monitor实际提示为准）；Ctrl+C退出并释放串口。

服务器重启后才使用新日志代码。保留现有启动脚本与环境变量；以原个性化语音启动器为例，另开PowerShell：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
$latencyStamp = Get-Date -Format yyyyMMdd_HHmmss
& .\server\tools\start_ai_bridge_gpt_sovits.ps1 *> ".\server\voice_latency_$latencyStamp.log"
```

这会按该脚本原配置启动服务并保存输出，不是把新manbo音色接入。若8000已被占用，先识别原服务，不要重复启动或随意结束进程。测试时同时保存ESP日志、服务日志、固件版本、后端配置、参考声音与冷热启动状态。先核对同ID事件，再采集至少20～50轮计算P50/P90。

## Git范围

本项目已建立本地Git。每阶段验证和文档更新后提交。真实`main\network_config.h`不入库，换电脑时从`main\network_config.example.h`复制并自行填写；录音、模型、构建缓存不入库。本地原文件不删除。GPT-SoVITS安装目录位于项目外，本仓库不会自动备份其外部代码/权重。提交与远程推送状态见最新task_progress。

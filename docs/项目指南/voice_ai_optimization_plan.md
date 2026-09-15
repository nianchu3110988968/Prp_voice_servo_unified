# 语音 AI 链路优化方案

本文记录 2026-09-01 之后的语音交互优化方向。当前基础链路已经跑通：

```text
ESP32 唤醒 -> 录音上传 -> ASR 识别文字 -> 生成回复 -> TTS 生成语音 -> ESP32 下载播放
```

当前主要问题：

- TTS 还是 Windows SAPI 临时音色，不符合最终“自设计音色”目标。
- 回复生成默认仍以规则逻辑为主，语言风格单一。
- 录音按固定时长截断，遇到短句、长句、停顿、犹豫时容易出错。
- ASR 准确率需要基于真实录音继续优化。

## 一、自定义音色方向

### 目标

最终语音不只是“能读出来”，而是有明确角色感：柔软、低压力、可爱、治愈，适合毛绒陪伴机器人。

### 推荐路线

1. 短期验证：保留当前 Windows SAPI 后端作为兜底，同时新增可切换 TTS 后端接口。
2. 第一版自定义音色：优先试 GPT-SoVITS 或 CosyVoice 的零样本/少样本克隆能力。
3. 最终音色定型：录制一套干净、授权明确、风格统一的声音素材，再做少样本微调或固定提示音色。

### 数据准备建议

- 先录 30 到 60 条短句，每条 3 到 8 秒。
- 文本覆盖：安慰、陪伴、确认、轻微撒娇、提醒休息、表达开心、拒绝危险请求。
- 声音要求：安静环境、距离固定、音量稳定、不要混响、不要背景音乐。
- 标注要求：每条音频对应精确文本；后续可以增加风格标签，如 `healing`、`cute`、`quiet`、`encourage`。

### 接入方式

服务端不要让 ESP32 直接关心 TTS 模型。保持现有接口：

```json
{
  "reply_text": "...",
  "motion": "comfort",
  "audio_url": "/recordings/reply_xxx_16000hz.wav"
}
```

改造重点放在服务器：

- `server/services/tts_service.py` 改成统一入口。
- 新增不同后端，例如 `windows_sapi`、`gpt_sovits`、`cosyvoice`。
- 所有后端最终都输出 ESP32 可播放的 `16 kHz / 16 bit / mono WAV`。
- ESP32 仍然只下载 `audio_url` 并播放，不需要知道背后换了什么模型。

当前状态（2026-09-07）：服务端已实现 `windows_sapi` 与 `gpt_sovits` 可切换入口、GPT-SoVITS WAV 规范化及 SAPI 回退；默认仍为 `windows_sapi`。实际音色训练、GPT-SoVITS API 启动和真实音频验证尚未完成。

## 二、回复理解与语言风格

### 目标

从“关键词触发固定话术”升级为“能理解语境、能切换风格、能给动作意图”的陪伴式对话。

### 推荐路线

1. 启用本地 LLM 后端，例如 Ollama。
2. 把回复生成从单一字符串改为结构化结果：

```json
{
  "reply_text": "嗯，我听见啦。先把肩膀放松一点，我陪你慢慢来。",
  "style": "healing",
  "emotion": "comforting",
  "motion": "comfort",
  "safety": "ok"
}
```

3. 增加角色设定和风格控制：

- `healing`：温柔、安抚、低压力。
- `cute`：轻微可爱，但不过度幼稚。
- `quiet`：短句、轻声、适合睡前。
- `encourage`：鼓励、陪伴行动。
- `curious`：回应用户分享，继续追问一点点。

4. 增加短期上下文记忆：

- 保留最近 3 到 5 轮对话。
- 只保留简短文本，不在 ESP32 侧保存。
- 后续可以增加用户偏好摘要，例如“不喜欢太夸张的语气”“晚上使用时要短一点”。

### 安全边界

- 不做医学诊断。
- 不承诺治疗效果。
- 遇到强烈自伤、危险、急症内容时，回复应鼓励联系现实中的可信任的人或专业帮助。
- 回复必须短，优先适合语音播放。

## 三、录音与 ASR 优化

### 当前问题

固定录音 5 秒太机械：

- 用户说短句时，会录入过多静音，增加延迟。
- 用户说长句时，可能被截断。
- 用户中途停顿、犹豫时，可能提前结束或截到半句。

### 推荐路线

第一阶段先在 ESP32 侧做轻量端点检测：

- 唤醒后先进入“等待开始说话”状态。
- 检测到声音超过阈值后开始正式录音。
- 连续静音超过 800 到 1200 ms 后结束录音。
- 设置最大录音时长，例如 8 到 10 秒，避免无限等待。
- 设置最小录音时长，例如 700 ms，避免误触发上传。

第二阶段在服务端启用或加强 VAD：

- `faster_whisper` 打开 `vad_filter`。
- 根据实际录音调整静音阈值、最小语音时长、最大静音时长。
- 保存每次录音的音量峰值、识别文本、耗时，用于对比优化。

第三阶段优化 ASR 模型：

- 先把 `tiny` 和 `base` 进行同一批录音对比。
- 如果电脑性能允许，再试 `small`。
- 对普通话短句，可以评估 SenseVoiceSmall。
- 建立 20 到 50 条真实测试录音，记录期望文本和实际识别结果。

## 四、建议推进顺序

1. 先做可观测性：记录每次交互的 ASR 文本、回复文本、TTS 后端、耗时、音量统计。
2. 再做回复能力：把 `LLM_BACKEND` 从规则回复切到 Ollama，并让回复输出结构化 JSON。
3. 再做录音端点检测：把固定 5 秒录音改为“开始说话 + 静音结束 + 最大时长兜底”。
4. 再做 ASR 对比测试：用同一批录音比较 `tiny/base/small` 和 VAD 参数。
5. 最后接入自定义 TTS：先本地服务验证音色，再替换 `tts_service.py` 后端。

## 五、下一次优先任务

建议先做“服务端回复生成升级”：

- 改 `server/services/dialogue_service.py`。
- 增加风格参数和结构化输出。
- 保留规则兜底。
- 不影响 ESP32 当前播放链路。

理由：这一步不需要动板子、不需要重烧录，风险低，体验提升明显。

## 六、2026-09-02 已落地实现

第一版先只做两种差异明显的风格：

- `cute`：轻微可爱、软一点、亲近一点，但不过度幼稚。
- `encourage`：更坚定、更有支撑感，给很小的行动建议。

当前实现位置：

- `server/server_config.py`：通过 `REPLY_STYLE` 配置 `auto`、`cute` 或 `encourage`。
- `server/services/dialogue_service.py`：统一生成 `reply_text`、`style`、`emotion`、`motion`，并保留规则兜底。
- `server/ai_bridge_server.py`：接口返回中新增 `reply_style`、`reply_emotion`、`llm_detail`。

当前保持 ESP32 兼容，已有的 `reply_text`、`motion`、`audio_url` 字段不变。下一步用本地服务端接口测试几轮文字输入和真实录音，确认两种风格差异是否符合预期。

## 七、大模型接入方式

当前服务端已经配置为“大模型优先，规则兜底”：

- 默认后端：`LLM_BACKEND = "ollama"`。
- 默认模型：`OLLAMA_MODEL = "qwen2.5:3b"`。
- 默认地址：`OLLAMA_URL = "http://127.0.0.1:11434/api/generate"`。
- 默认超时：`OLLAMA_TIMEOUT_SECONDS = 90`。
- 默认保持加载：`OLLAMA_KEEP_ALIVE = "10m"`。
- 如果 Ollama 未安装、未启动或模型未拉取，服务端不会崩溃，会返回规则兜底回复，并在 `llm_status` 中标记 `fallback_ollama_error`。

配置位置：

```text
E:\Projects2026\Prp_voice_servo_unified\server\server_config.py
```

可以通过环境变量临时切换，不必改代码：

```powershell
$env:PRP_LLM_BACKEND='ollama'
$env:PRP_OLLAMA_MODEL='qwen2.5:3b'
$env:PRP_REPLY_STYLE='auto'
$env:PRP_OLLAMA_TIMEOUT_SECONDS='90'
```

安装并启动 Ollama 后，需要拉取模型：

```powershell
ollama pull qwen2.5:3b
```

启动电脑服务器：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python -m uvicorn ai_bridge_server:app --host 0.0.0.0 --port 8000
```

测试服务端配置：

```powershell
curl http://127.0.0.1:8000/config
```

测试文本回复：

```powershell
curl "http://127.0.0.1:8000/debug/dialogue?text=我今天压力好大"
```

## 八、2026-09-13 “糯糯”角色提示词第一版

用户提供的角色设定已原样保存为：

```text
server/prompts/nuonuo_v1.txt
```

当前实现约定：

- `server/services/dialogue_service.py` 从独立文件加载角色设定，再附加语音长度、情绪回应、安全边界和 JSON 输出要求。
- 角色名通过 `PERSONA_PROMPT_NAME` 回传，调试响应可确认本轮实际使用的人设。
- `cute/encourage` 仍是当前情境模式，但不能覆盖“糯糯”的固定身份。
- 最近四轮对话继续用于短期一致性；服务重启后历史会清空。
- 负面情绪下禁止用“好耶”“真的假的啦”“那必须的”等开场，也不应使用“别担心”“开心点”等空泛安慰。
- 服务端会根据用户文本校正 `emotion/motion`，避免焦虑内容被模型错误标成 `happy`。

默认配置：

```text
PRP_PERSONA_PROMPT_NAME=nuonuo_v1
PRP_PERSONA_PROMPT_FILE=server/prompts/nuonuo_v1.txt
```

以后新增人设时，新建另一个 UTF-8 文本文件并切换以上环境变量即可，不需要修改对话业务代码。

第一轮文本测试已验证：模型能自称“糯糯”、识别压力/焦虑/开心等情境，并输出与情绪一致的动作字段。语言自然度仍需由用户试听评价，本轮不把五条样例表述成正式效果指标。

## 九、2026-09-13 ASR 第一轮升级

原配置为 `faster-whisper tiny / CPU int8 / beam 3`。真实日志出现错字、漏字和繁体字，例如：

```text
我在玩播放新雄鐵道
困惯,我要写掉
```

当前默认改为：

```text
model=small
compute_type=int8
beam_size=5
best_of=5
condition_on_previous_text=false
initial_prompt=""
hotwords=""
```

并增加 `opencc-python-reimplemented`，统一把识别结果转换为简体中文。同一批旧录音的非正式复查中，`small` 能输出更合理的“我在玩崩坏星球铁道”和“困了，我要睡觉”，热启动单条约 1.6～1.8 秒；首次加载约 4～5 秒。由于部分旧录音缺少人工记录的标准文本，这只能证明输出明显改善，不能直接计算正式 CER。

完整提示词或过强热词会在短而含糊的录音中诱发幻听，因此两者默认关闭，仅保留以下环境变量供后续受控实验：

```text
PRP_ASR_MODEL_NAME
PRP_ASR_BEAM_SIZE
PRP_ASR_BEST_OF
PRP_ASR_INITIAL_PROMPT
PRP_ASR_HOTWORDS
```

新增量化脚本：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python tools\benchmark_asr.py asr_manifest.csv
```

清单必须是 UTF-8 CSV：

```csv
audio_file,reference
recordings/recording_001.wav,我今天压力好大
recordings/recording_002.wav,困了我要睡觉
```

脚本输出每条识别文本、耗时、CER，以及整批语料的总 CER 和整句正确率。正式结论需收集至少 20～50 条带人工标准文本的真实录音，再比较 `tiny/base/small`。

## 十、连续对话与响应速度

连续对话原本已经实现，但旧配置仅允许 3 轮、每轮等待开口 6 秒，用户稍作停顿就会退出，因此体验上像是不能连续回复。当前固件配置已改为：

```text
AI_CHAT_CONTINUE_ENABLED=1
AI_CHAT_MAX_FOLLOWUP_TURNS=8
AI_CHAT_FOLLOWUP_TIMEOUT_MS=30000
```

实际语义是：首次唤醒并完成一轮回复后，机器人继续监听；回复播放结束后 30 秒内再次开口，无需重新说唤醒词。连续完成最多 8 轮，或者 30 秒没有检测到新语音时返回唤醒模式。该代码已编译但尚未烧录实测。

当前响应链路只能串行执行：

```text
句尾静音判定 → 上传 → ASR → LLM → TTS → 返回 JSON → 下载完整 WAV → 播放
```

已落地的第一批优化：

- 服务启动时预加载 `faster-whisper small`，并用空请求让 Ollama 模型进入 `keep_alive`；本机实测两者启动预热总计约 3.1 秒，避免把首次加载时间算进第一次对话。
- Ollama 保持加载 10 分钟；预热后的文本回复测试约 0.56～1.2 秒。
- ESP32 新增请求往返耗时日志，并解析服务器返回的 ASR、回复、TTS、总耗时，方便定位瓶颈。
- 服务器日志新增实际 ASR 模型和角色提示词名称。

当前硬件为 RTX 4060 Laptop 8GB，但 `faster-whisper` CUDA 测试因缺少 `cublas64_12.dll` 尚不能启用 GPU。当前 `small/CPU/int8` 热启动单条约 1.6～1.8 秒。后续优化优先级：

1. 先采集真实端到端 P50/P90，确认时间主要消耗在 ASR、LLM、GPT-SoVITS还是音频下载。
2. 补齐兼容的 CUDA 12/cuBLAS/cuDNN 后测试 `small/float16 GPU`，同时保留 CPU 回退。
3. 保持回复短句并让 Ollama、ASR、GPT-SoVITS常驻，避免反复加载模型。
4. 第二阶段改造 GPT-SoVITS 流式输出和 ESP32 边下载边播放；这是降低“听到第一声音时间”的主要结构性方案。
5. 不盲目并行 ASR、LLM、TTS，因为后两步依赖前一步结果；可以并行的是模型预热、连接建立和不依赖文本的准备工作。

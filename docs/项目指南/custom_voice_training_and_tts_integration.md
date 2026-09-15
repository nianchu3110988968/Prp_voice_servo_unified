# 自定义音色训练与接入说明

> 2026-09-15 整理后：唯一当前数据在 `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo`，实验名统一 `manbo`。39段切片与最后提交中文已保留；旧manbo模型、缓存和日语批次已移入回收站，新实验尚未格式化/训练。操作入口见 `E:\Projects2026\Prp_voice_servo_unified\docs\项目指南\GPT-SoVITS网页训练教学.md`。本文旧实验路径和旧运行状态仅为历史，第7节本人参考语音零样本链路与官方底模保留。

## 1. 目标与链路

使用经过授权的个人声音素材训练或微调中文 TTS 音色，并接入电脑服务端。ESP32 继续只接收并播放 WAV，不需要了解 TTS 模型，也不需要因为更换音色而重新烧录。

```text
ESP32 唤醒与录音 -> faster-whisper -> Ollama 生成回复
-> GPT-SoVITS 合成自定义音色 -> 统一为 16 kHz/16 bit/mono WAV
-> ESP32 下载 /recordings/reply_xxx.wav 并播放
```

服务端已完成适配，个人声音的参考音频零样本克隆曾验证成功；旧manbo微调模型因质量问题已清理。实际运行后端以当次启动配置及 `/config` 为准，不能把早期 Windows SAPI 默认值当成当前服务状态。

## 2. 训练阶段

推荐 GPT-SoVITS，适合中文和少量数据的音色验证。先用参考音频做零样本或少样本推理，确认音色方向和电脑性能，再整理数据集训练或微调。

数据建议：

- 只使用本人声音，或取得声音所有者明确授权。
- 初步验证准备 1 至 3 分钟；正式音色建议 10 至 30 分钟。
- 每段 3 至 10 秒，单人、单句、配准确文本。
- 安静环境、固定距离、音量稳定；避免音乐、风噪、混响、削波和多人说话。
- 内容覆盖陪伴、安慰、确认、提醒休息、开心和普通问答等实际场景。

训练产物需要能由 GPT-SoVITS API 使用。模型训练本身在 GPT-SoVITS 工程中完成，不在本项目固件中完成。

## 3. 服务端配置

### 3.1 将 M4A 转为参考 WAV

本项目提供转换脚本。它不会修改原始 M4A，只生成 16 kHz、16 bit、单声道 PCM WAV：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python tools\convert_reference_audio.py `
  'C:\Users\ASUS\Downloads\20260907_003026.m4a' `
  'E:\voice_models\reference_20260907.wav'
```

本次录音对应的参考文本就是用户提供的整段荣宅讲解文字。参考文本必须与音频中实际说出的内容完全一致。40 秒左右的整段录音可用于初步推理；正式训练时应再按句切分成 3 至 10 秒的小片段并逐条标注。

在启动服务端的 PowerShell 窗口中设置：

```powershell
$env:PRP_TTS_BACKEND='gpt_sovits'
$env:PRP_GPT_SOVITS_URL='http://127.0.0.1:9880/tts'
$env:PRP_GPT_SOVITS_REFERENCE_WAV='E:\voice_models\reference.wav'
$env:PRP_GPT_SOVITS_PROMPT_TEXT='参考音频中实际说的文字'
$env:PRP_GPT_SOVITS_PROMPT_LANGUAGE='zh'
$env:PRP_GPT_SOVITS_TEXT_LANGUAGE='zh'
$env:PRP_TTS_FALLBACK_TO_SAPI='true'
```

环境变量只对当前 PowerShell 窗口及其启动的服务进程有效。修改后必须停止旧 uvicorn 进程并重新启动服务端；不需要重启电脑或重新烧录 ESP32。

当前安装的 GPT-SoVITS 使用 `api_v2.py`，接口参数名为 `text_lang` 和 `prompt_lang`，语言代码使用 `zh`。项目适配器会兼容把“中文”等名称转换成 API 代码。

## 4. 测试

先关闭 `9872` 的推理 WebUI以释放显存，再分别在两个 PowerShell 窗口启动 GPT-SoVITS API 和本项目服务端：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
.\server\tools\start_gpt_sovits_api.ps1
```

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
.\server\tools\start_ai_bridge_gpt_sovits.ps1
```

检查配置并生成测试语音：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/config
Invoke-RestMethod 'http://127.0.0.1:8000/debug/tts?text=你好，我会一直陪着你'
```

预期 `/debug/tts` 返回 `status=ok`、`backend=gpt_sovits` 和 `/recordings/reply_xxx_16000hz.wav`。若 GPT-SoVITS 不可用且开启回退，会返回 `backend=gpt_sovits_fallback_windows_sapi`，表示链路正常但实际声音仍是 SAPI。

确认调试接口成功后，再使用 ESP32 做完整测试。服务端日志中的 `tts=ok/gpt_sovits` 才是实际使用自定义音色的证据。

## 5. 实现位置

- `server/server_config.py`：TTS 后端、GPT-SoVITS 地址、参考音频和语言配置。
- `server/services/tts_service.py`：统一入口、GPT-SoVITS 请求、WAV 格式转换和 SAPI 回退。
- `server/ai_bridge_server.py`：`/config` 配置回显和 `/debug/tts` 调试接口。

## 6. 故障判断

- `WinError 10048`：8000 端口已有旧 uvicorn 进程，不要重复启动；停止旧进程后再启动。
- `reference wav not found`：参考音频路径错误，使用绝对路径并确认文件存在。
- `gpt_sovits_fallback_windows_sapi`：API 不可达、参数不匹配、模型未加载或参考音频未配置；查看返回的 `detail` 和服务端日志。
- ESP32 播放失败：检查输出是否为单声道、16 bit、16 kHz PCM WAV；适配器会尝试统一该格式。

## 7. 当前本机音色与模型清单（2026-09-13）

当前已经实现并验证的是“官方 v2ProPlus 底模 + 用户自己的参考音频”的零样本个性化音色。它已经能够用用户的音色回复，不等于 Windows SAPI；但它还不是用十多分钟语料微调得到的新权重。

### 7.1 当前推理使用的官方底模

GPT 语义模型：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\GPT_SoVITS\pretrained_models\s1v3.ckpt
```

SoVITS 声学模型：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\GPT_SoVITS\pretrained_models\v2Pro\s2Gv2ProPlus.pth
```

当前启动配置：

```text
E:\Projects2026\Prp_voice_servo_unified\server\configs\gpt_sovits_v2proplus.yaml
```

### 7.2 当前用户参考音频

长参考音频：

```text
E:\Projects2026\Prp_voice_servo_unified\server\voice_models\reference_20260907.wav
```

当前 AI bridge 实际使用的短参考音频：

```text
E:\Projects2026\Prp_voice_servo_unified\server\voice_models\reference_short_20260907.wav
```

### 7.3 当前用户微调权重

截至 2026-09-13，下面两个 v2ProPlus 用户权重目录均为空，说明尚未生成用户微调模型：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\GPT_weights_v2ProPlus
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2ProPlus
```

不要把 `pretrained_models` 中的官方底模、`server/voice_models` 中的参考 WAV 和训练后生成的 `.ckpt/.pth` 混为一类。

## 8. 使用新语料训练 v2ProPlus 模型

本次准备的原始素材为：

```text
C:\Users\ASUS\Downloads\11_曼波10分钟台词(1)\taici.MP3
```

已检查为 MP3、44.1 kHz、双声道、约 783.75 秒（13 分 03.75 秒）。用户随后确认该素材为日语。同目录暂时没有台词标注文件，因此必须先切分、使用日语 ASR 自动识别并人工校对，不能按普通话素材处理或直接训练。

### 8.1 训练前释放显存

正式训练前应停止 AI bridge、GPT-SoVITS API 和 Ollama，避免 RTX 4060 Laptop 8GB 显存不足。停止这些服务不会删除模型或改变 ESP32 固件。

### 8.2 启动训练 WebUI

```powershell
cd E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604
.\go-webui.ps1
```

默认主界面地址：

```text
http://127.0.0.1:9874
```

实验/模型名建议只使用英文、数字和下划线。本次建议：

```text
nuonuo_mambo_v1
```

训练全过程必须始终选择：

```text
v2ProPlus
```

### 8.3 切分音频

在 `0-前置数据集获取工具 -> 0b-语音切分工具` 中填写：

```text
输入：C:\Users\ASUS\Downloads\11_曼波10分钟台词(1)\taici.MP3
输出：E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\output\nuonuo_mambo_v1\slicer
```

第一轮保留界面默认参数即可：

```text
threshold=-34
min_length=4000
min_interval=300
hop_size=10
max_sil_kept=500
max=0.9
alpha_mix=0.25
```

理想切片约 3 至 10 秒，单句、无截字、无过长静音。背景音乐、明显混响或他人声音需要先处理；干净单人录音不要盲目降噪，以免损伤音色。

### 8.4 自动识别并校对日语文本

在 `0c-语音识别工具` 中，将切片目录作为输入，输出建议使用：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\output\nuonuo_mambo_v1\asr
```

本素材必须选择支持日语的 ASR，例如 `Faster Whisper（多语种）`、语言 `ja`；不能使用界面默认的中文 FunASR。完成后，在 `0d-语音文本校对标注工具` 打开生成的 `.list` 文件，逐条试听并校正错字、漏字、多字和标点。人工校对是训练质量的关键步骤，未经校对的自动识别文本不应直接用于训练。

2026-09-13 曾误用中文 FunASR 生成一份包含大量错字和 23 条空文本的 `slicer.list`。该文件已判定无效，不得进入格式化或训练；原始 MP3 和 160 个音频切片仍可继续用于正确的日语标注。

### 8.5 格式化训练集

进入 `1-GPT-SoVITS-TTS`：

```text
实验/模型名：nuonuo_mambo_v1
训练模型版本：v2ProPlus
```

在 `1A-训练集格式化工具` 中填写已经校对的 `.list` 文件和切片音频目录，然后运行“训练集格式化一键三连”。成功后应生成：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\logs\nuonuo_mambo_v1
```

其中应包含以 `2`、`3`、`4`、`5`、`6` 开头的中间文件或目录。

### 8.6 微调 SoVITS 和 GPT

进入 `1B-微调训练`，先训练 SoVITS，再训练 GPT。RTX 4060 Laptop 8GB 第一轮建议：

```text
GPU：0
版本：v2ProPlus
SoVITS batch_size：4；total_epoch：8；每 4 轮保存
GPT batch_size：4；total_epoch：15；每 5 轮保存
DPO：关闭
```

如果显存不足，把 batch size 降到 2；不要优先增加训练轮数。十多分钟小数据集训练轮数过高容易过拟合，应保留多个保存点试听比较。

训练完成后的成对权重应出现在：

```text
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\GPT_weights_v2ProPlus\*.ckpt
E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2ProPlus\*.pth
```

同一个实验的 GPT 与 SoVITS 权重应配对使用，不要混用不同人物、不同版本或来源不明的权重。

## 9. 多模型保存与切换

可以长期保留多个模型。建议模型名包含人物、素材版本和训练批次，例如：

```text
nuonuo_mambo_v1
nuonuo_soft_v2
nuonuo_story_v1
```

### 9.1 临时热切换

GPT-SoVITS API 支持在 9880 运行期间切换权重，不必重新烧录 ESP32：

```powershell
$gpt = [uri]::EscapeDataString('E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\GPT_weights_v2ProPlus\模型文件.ckpt')
$sovits = [uri]::EscapeDataString('E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\SoVITS_weights_v2ProPlus\模型文件.pth')

Invoke-RestMethod "http://127.0.0.1:9880/set_gpt_weights?weights_path=$gpt"
Invoke-RestMethod "http://127.0.0.1:9880/set_sovits_weights?weights_path=$sovits"
```

两个接口都应返回：

```json
{"message":"success"}
```

热切换只对当前 9880 进程有效，重启服务后会恢复 YAML 中配置的权重。

### 9.2 持久切换

要让电脑重启后仍默认使用指定模型，修改：

```text
E:\Projects2026\Prp_voice_servo_unified\server\configs\gpt_sovits_v2proplus.yaml
```

将 `custom` 下的两个字段改为目标权重：

```yaml
custom:
  t2s_weights_path: GPT_weights_v2ProPlus/目标模型.ckpt
  vits_weights_path: SoVITS_weights_v2ProPlus/目标模型.pth
```

保存后重启 9880。仅切换 GPT/SoVITS 权重时，ESP32 无需烧录；若还要切换参考音频和参考文本，则需要让 AI bridge 使用对应的参考配置并重启 8000。

第一批训练完成后，建议在项目中建立模型注册表和按名称切换脚本，将“权重对、参考音频、参考文本、版本”绑定成一个配置，避免手工混配。

## 10. RVC 模型能否接入

可以接入，但 RVC 模型不能直接填入 GPT-SoVITS 的权重字段。RVC 是语音转换模型，输入必须先是一段已有语音；当前 GPT-SoVITS 是文字转语音模型。接入 RVC 后的链路应为：

```text
回复文字 -> 基础 TTS 生成语音 -> RVC 转换音色 -> 统一为 16 kHz/16 bit/mono WAV -> ESP32 播放
```

下载的 RVC 模型通常至少包含 `.pth`，最好同时有匹配的 `.index`。还必须确认其 RVC 版本、采样率、F0 方法及使用授权。当前项目尚未安装 RVC 推理环境，`server/services/tts_service.py` 也只支持 Windows SAPI 和 GPT-SoVITS，因此下载后的 RVC 权重目前不能直接投入项目。

如果后续接入，建议增加独立的 RVC 后处理服务与模型注册表，而不是覆盖 GPT-SoVITS：

```text
windows_sapi / gpt_sovits -> rvc_voice_conversion -> reply WAV
```

这样可以保留现有 GPT-SoVITS 音色，并按配置切换不同 RVC `.pth + .index` 模型。代价是增加一次推理，端到端延迟通常会高于直接使用 GPT-SoVITS。

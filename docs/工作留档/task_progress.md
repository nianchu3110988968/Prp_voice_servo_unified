# 任务进度记录

用于切换 agent 或中断后快速接续。每次完成阶段性任务后，用简短语言更新本文件。

## 2026-09-15：完整语音分段延迟与Git建库（最新）

- 用户本轮优先事项为补日志，不是接入新音色；已暂停前一轮音色接入讨论，没有更换生产TTS权重、参考声音或启动/重启语音服务。
- 固件代码版本`2026-09-15-latency-v1`：新增`main/voice_trace.h/.cc`，每轮随机请求ID，记录录音返回、请求开始/结束、PCM上传开始/写完、JSON收到/解析、下载开始/结束、播放API开始/结束。`main.cc`、`ai_client.h/.cc`、`audio_reply_player.h/.cc`传递trace并输出汇总；缺失阶段为-1，失败结果与成功分开。
- 上传完成不是HTTP请求返回：`main/CMakeLists.txt`链接`--wrap=esp_transport_write`，只在本请求任务的HEADERS_SENT后累计正数写入；参数/返回值透传，不改`esp_http_client_perform`、重试/超时或SDK包。多次尝试记录attempts，保留最后一次尝试时间；真实网络边界仍待上板确认。
- 服务端新增`services/latency_trace.py`，`ai_bridge_server.py`保持原业务流程，合法`X-Request-ID`原样回显。`timings_ms`保留asr/dialogue/tts/total_pipeline，新增body_receive/prepare_audio/total_request；同ID结构化日志关联录音和回复音频文件。双方用各自单调时钟，不跨设备直接减绝对时间。
- 功能不变范围：未改录音阈值、连续对话逻辑、请求/下载缓冲、超时、动作顺序和先下载完整WAV再播放流程。日志有少量开销；播放边界是软件API，不能冒充声学首尾声测量。
- 已验证：Python语法检查通过；服务端5项新离线回归与2项既有数据测试共7项通过；MSVC编译真实`voice_trace.cc`的主机模拟通过，覆盖写入透传、分块、错误、任务隔离、重试和缺失阶段。无真实ASR/LLM/TTS请求、无串口/硬件测试。
- 最终`platformio run`通过（RAM48,604/327,680字节，14.8%；Flash1,478,107/2,048,000字节，72.2%）。建空Git仓库曾触发ESP-IDF读取未出生HEAD失败，初始化提交后重建成功。已通过ELF反汇编确认`esp_http_client_write`实际调用`__wrap_esp_transport_write`，原`esp_transport_write`仍保留。本轮未烧录；板上版本未重新读取，不推断已更新。
- 已新增`docs/项目指南/voice_latency_logging.md`，更新文档索引、结构地图、录音端点说明；根`AGENTS.md`与工作记忆记录每阶段验证、提交、推送规范。
- 用户确认项目Git身份`nianchu3110988968 <nianchu3110988968@gmail.com>`，仅配置本项目。已验证GCM登录账号一致，并经用户确认创建私有仓库`https://github.com/nianchu3110988968/Prp_voice_servo_unified`，origin已配置。初始化提交`dd52dc1`；功能阶段提交`c62c8e3`已推送至origin/main，包含现有项目基线与新增延迟观测代码。
- `.gitignore`排除真实网络配置、录音、模型、构建/运行缓存；保留原本地文件，不删除。新增`main/network_config.example.h`供克隆后填写，不更改现有`network_config.h`。项目外GPT-SoVITS安装目录和模型不在此Git仓库范围内，需另外备份。
- 下一步：经用户另行确认烧录后，采集首轮/连续轮次及失败分支，确认VOICE_CORRELATION match=1、每轮事件完整、时序单调，再做20～50轮P50/P90统计。当前8000/9880没有监听，本轮没有启动或重启它们，服务器新日志也未做真实模型联调；不能把本轮模拟测试记成真实端到端性能结果。

## 2026-09-15：manbo 数据收敛与工作规范（最新状态）

- 用户确认校对修改均已提交后，先保留最新39条中文，验证音频/标注映射，再停止旧9874/9873/9871服务并清理。当前唯一数据目录为 `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo`：`clips\001.wav`～`039.wav`、`clips.list`、`full_audio.wav`、`full_text.txt`；`dataset.json`溯源和`README.md`操作说明。
- 标注采用2026-09-15 10:13:25的最后保存稿，不是更早训练缓存；迁移后39段SHA256与源记录相同，分句顺序/内容未变，迁移初始标注哈希复查一致。连续中文188.10秒，含尾静音的切片共197.85秒；无日语。250ms补静音不能宣称补回缺失字音。
- 按用户授权，将53项旧manbo素材、日语来源、旧模型/训练缓存、重复录音和日志移入Windows回收站，共6,941,844,963字节。审计：`E:\Projects2026\Prp_voice_servo_unified\docs\工作留档\manbo_cleanup_20260915.json`；53项均为recycled，原路径均不存在。未清空回收站，不能声称已释放磁盘容量。历史文档保留作追溯，其中旧输入路径已失效。
- 保留 `C:\Users\ASUS\Downloads\三月七`（RVC包，未接入）、项目`server\voice_models`个人参考音频与`server\configs`配置、GPT-SoVITS官方预训练权重/依赖。没有修改生产TTS配置，没有删除本人声音。本人旧声音链路是参考音频零样本克隆，不是另训权重。
- 全局新增 `C:\Users\ASUS\.codex\skills\local-path-handoff\SKILL.md`，并在`C:\Users\ASUS\.codex\AGENTS.md`强制规定：每次交付本地链接附完整可复制绝对路径和用途；GPT-SoVITS网页只能在用户外部浏览器操作。技能校验通过。外部Chrome当前未连接控制工具，未在Codex内置浏览器操作网页。
- 新入口 `server\tools\start_manbo_training.ps1`：实验名`manbo`，v2ProPlus，预填唯一数据路径，GPU0、SoVITS workers0/GPT workers1、保留TEMP，端口重复检查；只启动UI，不自动开浏览器/训练。GPT-SoVITS `webui.py`修改默认字段/标题、worker变量与自动打开行为；`tools\subfix_webui.py::b_save_list`仅在当前标注路径保存时同步整段稿，标题可辨识且不自动开网页。两文件旁保留`.before_prp_workspace_20260915`代码回退副本。`weight.json`清除已删除旧模型选择，回到官方底模。
- 当前仅训练主页9874运行（Python PID49792，启动器PID71200；重启后会变化）；HTTP `/config`验证标题`MANBO Training - 9874`、模型名/版本/新音频路径/标注路径正确。9871/9872/9873未开启；需要校对时由用户在主页面0d开启9871，保持单标签页。旧全局页码覆盖风险未修复，不得宣称跨窗口安全。
- 同时只读检查11434监听；8000/9880没有监听。本轮不是恢复机器人全链路，不擅自开启或切换生产服务。
- 验证：2项`server\tests\test_manbo_workspace.py`回归通过（39段音频/整段稿/哈希与隔离保存同步）；相关Python语法检查通过；启动器PowerShell解析通过；`platformio run`成功（RAM14.8%、Flash72.0%，有多版本PIO Core提示，未改变环境）。未修改ESP32源码，未烧录，未新增硬件实测。
- 新实验`manbo`尚未做1A特征提取、尚未训练、尚未试听验收/接入机器人。下一步：用户在外部浏览器检查唯一数据，确认无误后按新实验重建特征与训练；不要复用历史“已完成一键三连”的结论。

以下为历史阶段记录；若与上方最新状态冲突，以上方及当前文件/服务检查为准。

## 当前状态

- 日期：2026-09-13
- 项目：毛绒治愈机器人 PRP 统一工程。
- 工程路径：`E:\Projects2026\Prp_voice_servo_unified`
- 当前阶段：语音和单舵机链路已跑通，开始集中优化角色回复一致性与 ASR 准确率。

## 已完成

- 整理 `docs` 目录为 `项目指南`、`工作规范`、`工作留档` 三类。
- 新增 `docs/README.md` 作为文档入口。
- 新增本进度记录文件，作为后续交接入口。
- 新增 `docs/项目指南/voice_ai_optimization_plan.md`，记录音色、回复能力、录音/ASR 的优化方向和推进顺序。
- 服务端回复生成已加入 `cute` 和 `encourage` 两种风格模式，并返回 `reply_style`、`reply_emotion`，保持 ESP32 既有字段兼容。
- 已验证：`python -m py_compile server_config.py ai_bridge_server.py services\dialogue_service.py` 通过；样例回复调用通过；`platformio run` 编译通过。
- 服务端已配置为 Ollama 大模型优先，默认模型 `qwen2.5:3b`；新增 `/debug/dialogue` 文本回复调试接口。
- 已验证大模型配置读取正常：`llm_backend=ollama`、`ollama_model=qwen2.5:3b`、`reply_style=auto`；当前因本机 Ollama 服务未运行，回复会自动规则兜底。
- 已再次验证：服务端 Python 语法检查通过；样例回复调用通过；`platformio run` 编译通过。
- 本机 Ollama 已安装并启动，`qwen2.5:3b` 已拉取完成。
- 已处理服务端重复启动导致的 `WinError 10048`：旧 `8000` 端口进程已重启为当前代码版本。
- 已把 Ollama 请求超时改为可配置项，默认 `90s`，并设置 `keep_alive=10m`，避免首次加载模型时过早回退。
- 已验证 `/config` 返回 `llm_backend=ollama`、`ollama_timeout_seconds=90.0`、`ollama_keep_alive=10m`。
- 已验证 `/debug/dialogue?text=我今天压力好大` 走 Ollama 成功返回：`llm_status=ok`、`backend=ollama`。
- 用户随后自行测试 `/config` 和 `/debug/dialogue` 返回 200；PowerShell 显示中文乱码，但接口状态正常。
- 最新语音测试已到达当前服务端：日志显示 `192.168.43.48 POST /voice/interact 200 OK`，且语音链路返回 `llm=ok/ollama`；如果听感没变化，下一步重点看 ASR 识别质量、TTS 音色和前台日志观察方式。
- 已修正后台 uvicorn 日志中文乱码问题：服务启动时强制 stdout/stderr 使用 UTF-8，并对 AI bridge 日志 `print` 增加 `flush=True`。重启后新日志已能用 `Get-Content ... -Encoding UTF8` 正常显示中文。
- 已修复空 ASR 文本时规则兜底回复可能把列表传给 `reply_text` 的问题。
- 已再次验证：`python -m py_compile server_config.py ai_bridge_server.py services\dialogue_service.py` 通过；`platformio run` 通过；当前 `8000` 端口服务进程为后台 uvicorn。
- 新增 `docs/项目指南/recording_endpoint_detection.md`，记录 ESP32 端录音端点检测设计、配置项、日志和调参方式；后续修改录音逻辑必须同步维护。
- ESP32 端已实现 AI bridge 端点检测录音：保留旧固定时长函数，新增 `audio_recorder_record_pcm_endpoint()`，支持等待开口、pre-roll、最短/最长录音、连续静音结束和音量日志。
- `main/network_config.h` 已新增端点检测配置；`main/main.cc` 已按 `AI_RECORD_ENDPOINT_ENABLED` 开关选择端点检测或固定时长录音。
- 端点检测版本曾完成编译；其代码已随之后的统一固件烧录到板子，但尚缺按短句、长句、停顿和无语音场景形成的系统化测试记录。
- 用户烧录/测试后出现欢迎音后直接进入命令词模式。原因已定位：程序没有进入端点检测函数，而是 `ai_bridge_ready == false` 时静默回退到本地命令词模式；旧日志“准备开始 AI bridge 录音”打印在 ready 判断之前，造成误导。
- 已修复 AI bridge 进入前判断：每次唤醒时调用 `ensure_ai_bridge_ready()`，如果 Wi-Fi 已连接则恢复 `ai_bridge_ready`，如果不可用则明确打印 Wi-Fi 状态和服务器地址；欢迎音成功日志不再提前宣称准备录音。
- 固件版本号更新为 `2026-09-02-endpoint-v1`；修复后 `platformio run` 编译通过。
- 根据实测反馈继续优化端点检测：新增环境噪声基线采样和动态开始/停止阈值，降低嘈杂环境误触发并改善小声说话无法触发的问题。
- 新增连续对话配置与流程：一次唤醒成功后，最多继续等待 3 轮后续发言，每轮等待开口 6 秒；无后续语音则回到等待唤醒。
- 服务端新增 `timings_s` 返回字段，并在终端输出 `understand/reply/tts/total` 四项耗时，单位秒，保留一位小数。
- 固件版本号更新为 `2026-09-03-endpoint-v2`，用于区分动态阈值和连续对话版本。
- 已验证：服务端 Python 语法检查通过；`platformio run` 编译通过；后台服务器已重启并验证计时日志输出。

## 本阶段已完成

- 2026-09-15 根据用户要求保存项目结构图：截图快照保存至 `docs/assets/project_structure_map_snapshot_20260915.png`，新增可维护版本 `docs/项目指南/project_structure_map.md`，并在 `docs/README.md` 与 `docs/工作规范/agent_working_memory.md` 中加入维护约定。后续新建重要文档、增加功能模块、调整入口或改变链路时，需要同步更新该结构地图。本次仅修改文档与复制截图，未修改代码、未编译、未烧录。
- 2026-09-15 09:53 用户决定用尾静音版进行完整训练并要求打开模型训练网页。本轮已启动9874主WebUI（PID51132，日志`server/training_ui_20260915_095344.out.log`/`.err.log`），浏览器已进入1-GPT-SoVITS-TTS/1A，选择v2ProPlus，填写新实验名`manbo_narrator_zh_v3_tailpad`（启动前不存在），输入为素材目录`slicer_tailpad_20260915/training.list`和`audio`，三个GPU字段均为0。重新核验39个中文WAV哈希与导出报告相同，总文件时长197.85秒（含新增9.75秒静音，不等于增加有效语料），末段日语不引用。未点击一键三连、未开始微调、未选定本轮训练轮数；下一步应重新生成特征并逐条核对，再分阶段训练，不复用v1/v2缓存。
- 为后续训练释放显存，核实身份后停止原9872试听进程70008，9874保持运行；模型文件和生产配置不改。主WebUI启动会自动清理自身TEMP，本轮启动前已完整复制到GPT-SoVITS根目录`TEMP_backup_before_training_ui_20260915_095344`，含临时配置/缓存，均可从备份恢复；未主动清理训练目录。主服务继承`PRP_TRAIN_NUM_WORKERS=0`以降低SoVITS加载器内存占用；GPT网页训练默认配置num_workers仍为4，正式启动GPT前应采用此前验证的低worker方案，不能直接假定已调整。此次仅启动服务/填写页面/留档，没有修改代码、编译、训练或烧录。
- 尾静音保护版完成后 `platformio run`通过（31.94秒，RAM14.8%、Flash72.0%）；未修改ESP32代码，未烧录。40段文件结构、PCM保留、尾静音和39条标注路径核验通过，听感仍待用户测试。
- 2026-09-15 用户反映切片尾字像被吞掉并要求保持原分句重切。检查原`slicer`40段：按文件名采样起止点从源WAV重采样并复现原归一化，40段PCM均逐样本相同、长度一致；39个中文切点处为数字静音，旧尾部纯静音约20～30ms，切点后到下一段非微弱信号约125～265ms。原MP4解码为44.1kHz单声道PCM16与源WAV数据也完全一致（16,873,472字节）。这些证据不支持直接宣称“切片读丢半个字”，但结束余量偏短；播放端或原素材的具体发音问题尚待逐段人工对照。
- 新增 `server/tools/reslice_preserve_boundaries.py`：按原边界从完整WAV重导出，不重新分句/ASR、不淡出尾音、不引入下一句，仅追加250ms静音。输出独立目录 `E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\output\nuonuo_mambo_video_v1\slicer_tailpad_20260915`，`audio`含40个同名WAV，`training.list`保留修正版固定标注39条、文本/顺序/语言完全不变，只改路径；末段日语仍排除。`verification.json`记录输入/输出哈希与边界，验证新PCM前缀与旧版完全相同、附加部分全零、原文件未变。此为尾静音保护试听版，不是补回缺失音素，也不代表质量已验收；未重训、未替换网页参考或正式服务。目录README含具体复现命令与验收项。Python语法检查通过，固件构建结果另记。
- 2026-09-15 用户反馈官方底模+旁白参考的零样本试听未再出现重复，但音色/质感仍不理想；这是用户本次听感，不是已测得全量零重复率。建议优先筛选干净完整、风格一致的3～10秒参考；再受控比较官方GPT+修正版SoVITS e2/e4与全官方基线，不能预先保证声学微调不影响读字。维持相同架构、不新增后处理通常不会结构性增加推理步骤，实际耗时仍需同句多次测量；不优先重训GPT或增加RVC/超分链路。
- 已只读检查用户目录 `C:\Users\ASUS\Downloads\三月七`：`sanyueqi.pth`（55,223,738字节）、`added_IVF256_Flat_nprobe_1_sanyueqi_v2.index`（31,588,619字节）、空`train.log`，无GPT `.ckpt`或参考WAV。使用 `torch.load(weights_only=True,map_location='cpu')` 安全模式读取，未执行第三方脚本；元数据version=v2、f0=1、sr=40k、info=200epoch，457个weight条目，确认是RVC格式而非GPT-SoVITS权重，不能填入9872模型框。该文件夹未提供授权说明，来源/使用许可仍待核实。
- RVC接入须在TTS后追加音高/语音特征提取、可选索引检索及变声合成，当前项目没有此适配；模型常驻或GPU加速也不能保证零额外延迟。用户以不影响响应速度为前提，本轮未安装RVC、未加载运行该变声模型、未切换服务或模型，仅报告格式与方案。若寻找可直接替换的第三方音色，应优先同版本兼容的GPT-SoVITS权重对+参考音频/原文，并核实授权与实测热启动P50/P90。
- 零样本首条补充复核：large-v3/CPU/int8无提示识别为“你好 比较慢步 慢慢的步”，small识别为“一航 北京麦波 麦麦的波”。两个ASR均未转写出短语重复，但读字不稳定，不能据此替代人工听审、计算重复率或宣布已修复；音色及确切发音请以用户试听为准。
- 2026-09-15 08:17起经用户授权恢复“官方底模+旁白参考”的零样本试听。新增 `server/tools/start_manbo_zeroshot_webui.ps1`，明确指定官方s1v3与s2Gv2ProPlus、v2ProPlus、9872、禁止公网share、默认关闭CUDA Graph并拒绝端口重复启动。后台启动器PID71336，推理PID70008；日志 `server/manbo_zeroshot_20260915_081742.out.log`/`.err.log`。未启动训练、8000或9880，未改正式TTS YAML、未删改旧权重、未烧录。
- 本机外部 `GPT_SoVITS/inference_webui.py:1360` 新增 `PRP_DISABLE_CUDA_GRAPH=1` 控制初始勾选，1364显示原隐藏开关；原文件备份 `.before_prp_graph_control_20260915`。网页实见CUDA Graph未勾选，仍用普通GPU推理。Python语法检查及 `platformio run`通过（10.17秒，RAM14.8%、Flash72.0%）。启动日志“auto-enabled”是原硬件支持检查信息，不代表本次请求Graph启用。
- 已在9872浏览器实际上传固定清单索引10参考（6.60秒），填写精确原文“然后,点击开始创作,选择一个自己喜欢的背景颜色,这里主播选择的是黑色。”；top_k15/top_p1/temperature1、中文、语速1、复用结果关闭。网页实际生成“你好，我叫曼波，慢慢的波。”，保存 `server/recordings/manbo_zeroshot_20260915_sample01.wav`（32kHz单声道2.82秒）；另用同条件接口生成“你好，我是曼波。今天过得怎么样？你可以慢慢说，我会认真听着。”，保存同目录 `manbo_zeroshot_20260915_sample02.wav`（6.22秒）。第一条small无提示识别出现明显错字，不能据此宣称音质或读字验收通过；用户试听待反馈。本轮仅两条初步样例，尚未完成5句×3次受控比较；模型、参考、Graph均相对昨晚有变化，不能单独归因。操作入口及配置已更新训练教学文档首节。
- 2026-09-15 用户报告昨晚多次试听仍高概率重复词句，质量验收未通过；不再仅按偶发采样问题建议重试。已读取旧任务“开始 GPT-SoVITS WebUI 测试”及项目记录：最早个人声音是官方 `s1v3.ckpt + s2Gv2ProPlus.pth` 加约5.14秒本人参考音频的零样本推理，不是一句话微调出了模型。新旁白实验实际39段/188.10秒，SoVITS4轮、GPT5轮；两者流程、数据、参考与推理条件不同，不能直接认定训练越多越好。修正版已完成训练，但不等于音频质量合格。
- 本次重启后检查，相关端口只见11434监听，9872/9874/9880/8000未监听；未自行启动训练或修改生产配置。昨晚新增推理日志仍显示CUDA Graph路径，出现过旧v1 SoVITS切换记录后又加载回修正版，后续测试明确使用修正版GPT；不将全部问题归咎于误选v1。源码确认普通和CUDA Graph两条解码路径均已有默认1.35的语义token重复惩罚，不能把本问题解释为“没有开启防重复”；短文本还会在切句后重新合并，单纯改标点切句不保证有效。
- 下一步建议（尚未执行）：先固定同一旁白参考及原文、同一套参数、普通解码关闭CUDA Graph，对比官方GPT+官方SoVITS、官方GPT+修正版SoVITS e4、修正版GPT e5+修正版SoVITS e4（兼容版本受控对照，不随意混用不同音色/架构）。5条固定未训练句每条3次，保存音频、重复/漏字人工判定和耗时；必要时另比较修正版e2。再单独更换无刻意复读、句界完整的参考，或一次只调temperature等参数。官方基线稳定而微调恶化时优先保留稳定组合，不盲目增加轮数；均异常再排查参考匹配与推理实现。仅在对照结果支持时重新整理完整句界、准确标注的数据并多保存点微调。此次只核查并记录建议，无代码修改、训练、烧录或正式音色切换。
- 2026-09-15 用户反馈修正版推理将“慢慢的波”读两次。检查用户下载的 `C:\Users\ASUS\Downloads\audio.wav`（文件时间9月14日23:58，32kHz单声道3.86秒），本地small/CPU/int8无提示词识别为“你好 我叫曼波 慢慢的波 慢慢的波”，两处约1.98–2.54秒与2.76–3.40秒，与用户听感一致；推理日志中的目标输入、切句后文本及规范化文本均只含一次该短语，因此证据指向合成音频内部多生成，不是输入被重复拼接。当前网页参考文本为“有没有更简单、更快捷的方法，有的兄弟们有的。”，top_k=15、top_p=1、temperature=1，复用上次结果未勾选；网页目标已被用户改为“让我们放松一下”，不能将当前页面当作旧请求快照。短句/参考韵律/随机采样及CUDA Graph路径的具体影响尚未通过对照实验确定，不能断言训练失败或标注再次错配。本次仅诊断，未更改模型、页面参数或正式服务；降低采样随机性、更换正确配对参考片段和关闭CUDA Graph均只能作为后续对照项，不是已验证修复。
- 2026-09-14 23:53 修正版 `manbo_narrator_zh_v2_corrected` 已完成训练与电脑端实际合成：SoVITS `SoVITS_weights_v2ProPlus/manbo_narrator_zh_v2_corrected_e4_s80.pth`（23:46:12，4轮/80步）；GPT `GPT_weights_v2ProPlus/manbo_narrator_zh_v2_corrected-e5.ckpt`（23:49:03，5轮，日志明确 max_epochs=5 reached）。路径均相对 `E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604`。两份导出权重加载校验通过；GPT成功日志为实验目录的 `06_gpt_recovery.out.log`/`.err.log`。此前进程退出原因仍未确定，不能据此断言内存导致整机卡死。
- 修正版推理网页 `http://127.0.0.1:9872/` 当前 PID66320，已加载上述新权重。用固定训练清单第一段6.3秒中文音频及其正确对应文字作为参考，实际合成“你好，我是糯糯，今天也很高兴见到你。你可以慢慢说，我会认真听着。”，输出 `server/recordings/manbo_v2_corrected_audition_20260914.wav`：32kHz、单声道、16bit、5.78秒、369964字节；该次客户端完整合成调用9.14秒（单次首测，不代表机器人端到端延迟或P50/P90）。只验证合成成功与WAV结构，音色相似度、读字和自然度待用户试听。未切换正式机器人TTS，未烧录；旧v1及全部失败日志保留。训练自动跟进 `manbo` 已暂停，避免重复启动。
- 2026-09-14 23:47用户反馈机器似乎卡死。最新检查：所有Python训练/网页进程已退出，原流水线状态JSON仍停在running，退出原因无直接证据。SoVITS实际已于23:46:12完成第4轮并导出`manbo_narrator_zh_v2_corrected_e4_s80.pth`，CPU加载检查通过（678个权重项，info=4epoch_80iteration）；无需重训SoVITS。固定清单SHA256仍为`d83170b47d60a0d8beca81d9e84867816f9727c6d733a2c80cd4cb5a687728fe`。
- 已依据用户此前“自动下一步”授权，单独接续GPT5轮训练（PID43196），配置`logs/manbo_narrator_zh_v2_corrected/run_s1_recovery.yaml`，日志`06_gpt_recovery.out.log`/`.err.log`，batch4、workers1、官方GPT底模。不能重跑原流水线或依旧JSON误判SoVITS仍在训练；尚未验证GPT完成和新模型试听。
- 重训retry1第二轮保存失败的真实原因是`FileNotFoundError`：自动脚本遗漏创建网页原本负责建立的`logs_s2_v2ProPlus`目录，不是第二次内存不足。agent曾过早将其口头归因于内存，随后已明确纠正。已补建目录逻辑，将特征核验改为独立子进程（完成后释放Torch/文本库），SoVITS加载workers=0、GPT=1；仍保持batch4与4/5轮。retry2 PID46156，总日志`server/manbo_v2_pipeline_retry2.*.log`，旧尝试日志已归档。Python语法与`platformio run`再次通过，未烧录；最终训练结果仍待后续记录，不把重试启动视为完成。
- 修正版重训首次在SoVITS第1轮发生`DefaultCPUAllocator: not enough memory`（23:37:38），未产生checkpoint，流水线正确停下未进入GPT。已保留失败日志；在GPT-SoVITS的`GPT_SoVITS/s2_train.py`增加`PRP_TRAIN_NUM_WORKERS`覆盖项（默认仍5，原文件备份为`.before_prp_workers_20260914`），本次减为1个加载进程，GPT也改为num_workers=1，batch/轮数不变。项目脚本增加`--resume-validated`：仅允许失败状态、清单哈希不变且不存在训练checkpoint时重试，并先归档旧日志；不是续用污染v1模型。retry PID63648，总日志`server/manbo_v2_pipeline_retry1.*.log`。修改后Python语法检查与`platformio run`再次通过（RAM14.8%、Flash72.0%），未烧录。
- 2026-09-14 23:33 经用户明确授权已开始修正版重训，实验名`manbo_narrator_zh_v2_corrected`，全新目录、官方底模起步，绝不续用v1缓存/权重。训练输入为素材目录`train_manbo_v2_corrected/training.list`的固定副本，原校对`.list`未覆盖；另在副本中修正索引11“自带结尾”、14“文字转音频”、18“先生成”，改动依据保存在`text_corrections.json`。重识别抽查0/1/9/10/11/14/18/20/29用于验证串页对应关系，不冒充39条全量人工听审。
- 新增`server/tools/train_gpt_sovits_checked.py`：新实验存在则拒绝启动，记录39条音频路径/时长/哈希及标注；逐阶段检查退出码，重新提取全部特征后按固定清单重算音素/规范化文本/BERT长度进行逐条核对，再依次训练SoVITS4轮和GPT5轮，验证最终权重。流水线PID52704，状态`logs/manbo_narrator_zh_v2_corrected/pipeline_status.json`，总日志`server/manbo_v2_pipeline.*.log`，各阶段日志在新实验内；失败会停止，不自动跳过。已停止旧推理进程54824释放显存。Python语法检查通过，按规范已启动`platformio run`验证；没有烧录。
- 已建立本任务5分钟自动跟进（id=`manbo`）作为后台完成/失败提醒；流水线自己负责顺序执行训练，跟进不得重复启动。完成新权重加载和电脑端试听准备后应暂停该跟进；新音色暂不替换正式机器人服务。
- 2026-09-14 23:22～23:28 标注覆盖事故恢复：用户发现第10～19条文字写入第0～9条。已先备份原`.list`及整段正文到素材目录`recovery_20260914_232250`，从仍保留正确文本的内置浏览器第一页恢复前10条，并与22:51:02历史页面记录及00:11整段正文交叉核对；验证只改索引0～9，后29条近期修订保持不变，39个音频路径完全不变、无缺失。原音频未改、模型未删。
- 原因：`tools/subfix_webui.py`用进程全局`g_index/g_batch`保存页码，`b_submit_change`不接收提交页面自身索引；多窗口打开/翻页会相互改变写入位置。22:49 agent另开了9871内置浏览器页；此前记录的磁盘修改时间22:51:11、22:55训练文本特征的错配内容说明错误在训练前已发生，具体用户点击序列没有审计日志，不能断言是谁按了提交。agent此前只查数量/文件名，未检查逐段文本对齐，又把错误首条作为参考文本发给用户，需要纠正。
- 为阻止旧页继续写回，已停止旧9871校对进程68896，恢复后的校对服务临时改用9873（PID52440，日志`server/annotation_recovery_20260914_232250.*.log`）。后续只使用一个9873校对窗口，不要重启旧9871或在旧页提交。全局页码缺陷尚未改代码；新服务也不是多窗口安全版本。
- 重要更正：`manbo_narrator_zh_v1`虽然完成SoVITS4轮/GPT5轮训练，但其`2-name2text.txt`及文本特征使用了错配的前10条，故已有e2/e4/e5权重属于受污染试验，不可作为正确数据训练结果。已保留权重和缓存用于追溯；修复`.list`不会自动修复已生成缓存和模型。后续应使用新实验名重新格式化并从官方底模微调，不要在旧实验直接续训。本轮未重训、未接入机器人、未烧录。
- 2026-09-14 晚已核对用户完成的快速训练产物：SoVITS第4轮于23:09:52保存成功，导出 `manbo_narrator_zh_v1_e2_s40.pth` 与 `manbo_narrator_zh_v1_e4_s80.pth`；GPT导出 `manbo_narrator_zh_v1-e5.ckpt`（23:12:36）。检查时训练进程均已退出，用户1C截图已显示manbo权重路径。本次建议选择GPT e5 + SoVITS e4/s80，再开启独立9872推理WebUI；权重已导出，但新模型加载、用户试听与机器人接入尚未验证，不能将此前“未开始训练”当作当前状态。
- 2026-09-14 23:07 用户已启动 `manbo_narrator_zh_v1` 的 SoVITS 训练（23:06:27 启动）；实际配置为 batch4、4轮、每2轮保存、文本学习率倍率0.4、GPU0。最新日志确认 G/D 底模加载，进入首轮 `0/20` 批次进度；此时尚无完成轮数证据，GPT尚未启动。SoVITS轮数日志实际在 `E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604\logs\manbo_narrator_zh_v1\train.log`，逐批进度条写入本次 WebUI 的 `.err.log`；不是只看一键三连旧输出。
- 2026-09-14 晚用户将实验名改为 `manbo_narrator_zh_v1` 并完成一键三连；已检查最新产物：文本 39 行、semantic 39 条加表头，BERT/CNHubert/32k WAV/说话人特征各 39 个非空文件，文件名与正式中文清单一致，末尾日语未引用。此记录更新下面“尚未格式化”和旧实验名的历史状态；尚未开始 SoVITS/GPT 微调，检查时无训练进程且两个 v2ProPlus 导出目录为空。
- 新增 `docs/项目指南/GPT-SoVITS网页训练教学.md` 并加入索引，按本机页面与源码解释前处理、特征、双模型微调、推理、产物和续训；建议今晚快速版 SoVITS batch4/4轮/每2轮保存、GPT batch4/5轮/每5轮保存，GPU0、DPO关闭。约10～30分钟仅为未实测的时间预留，必须用首轮日志修正；参数未代用户设置，训练未代用户启动，新音色尚未试听或接入。项目级按名称成套切换模型仍未实现。本次仅修改文档，未改代码、未编译、未烧录。
- 2026-09-14 晚重启后已恢复训练主界面 9874 和校对界面 9871，浏览器已核验载入最新 39 条中文旁白标注。训练页已选择 `v2ProPlus`、实验名 `nuonuo_narrator_zh_v1`，填好标注/切片路径和单卡 `0`；尚未点击格式化或训练。Ollama 11434 已自动运行；为当前训练保留显存，9872 推理、9880 API、8000 AI bridge 未启动。启动日志为 `server/training_ui_20260914_224847.*.log` 和 `server/annotation_ui_20260914_224847.*.log`。
- 已处理视频素材 `C:\Users\ASUS\Downloads\曼波配音视频傻瓜式教学.mp4`：提取为 44.1 kHz 单声道 PCM WAV，并切成 40 段（总时长约 191.31 秒，单段约 3.21～6.60 秒）。用户确认使用其中的中文教学旁白训练，最后一段日语不加入。已用 `faster-whisper large-v3 / CUDA float16 / zh` 重识别前 39 段，生成 `output\nuonuo_mambo_video_v1\asr_large_v3_zh\mambo_tutorial_narrator.list` 与 `transcript_for_review.txt`；清单无空文本、无日语段。9871 标注 WebUI 已加载该清单，等待用户逐段试听校对；当前尚未格式化、尚未训练。
- 校对保存状态复查：Gradio 页面中的文字框不会自动写入 `.list`，每批翻页前必须点击 `Submit Text`；`Save File` 只保存已提交到服务端内存的内容。用户截图中的第 30～38 条修订曾只停留在浏览器输入框，现已由 agent 点击 `Submit Text` 并确认写入磁盘；第 0～29 条回看与磁盘均仍是旧自动识别稿，浏览器也没有 local/session storage 备份，需重新校对提交。此前基于未提交旧稿生成的 955 字符整段文本已改名为 `mambo_tutorial_audio_44100hz_mono_transcript_INVALID_pre_submit.txt`，明确不得使用；原始音频和 188.10 秒中文连续 WAV 均未改变。训练集尚未格式化、尚未训练。
- 2026-09-14 用户重新校对并逐批提交第 0～29 条；已核对 `mambo_tutorial_narrator.list` 更新时间为 00:10:23，共 39 条、无空文本，且关键修订词已真实写入磁盘。已据此重新生成正式单段文字稿 `source\mambo_tutorial_audio_44100hz_mono_transcript.txt`（UTF-8、单行、975 字符），与 `mambo_tutorial_narrator_zh_only.wav` 对应；先前 `INVALID_pre_submit` 文件仅保留作错误记录，不得使用。
- `faster-whisper large-v3`（约 2.88 GB）已下载完成，并成功为原日语素材 160 段生成 `output\nuonuo_mambo_v1\asr_ja\slicer.list`；该结果与本次中文旁白训练集相互独立，未合并。
- 用户确认新素材 `taici.MP3` 为日语；此前自动切分得到 160 段、约 710.96 秒有效语音，但误用中文 FunASR 生成的标注包含大量错字及 23 条空文本，已判定不得用于训练。原始音频和切片保留，训练暂停在标注阶段；若继续 GPT-SoVITS，应改用日语 ASR 并人工校对。已补充说明 RVC 不能直接作为 GPT-SoVITS 权重，需作为 TTS 后处理链路单独接入。
- 已检查新的训练素材 `C:\Users\ASUS\Downloads\11_曼波10分钟台词(1)\taici.MP3`：约 13 分 03.75 秒、44.1 kHz、双声道，时长足够进行第一版微调，但尚无逐句标注，需先切分、ASR 和人工校对。当前 `GPT_weights_v2ProPlus` 与 `SoVITS_weights_v2ProPlus` 均为空，尚无用户微调权重；多模型训练、存放和切换方法已补充到自定义音色指南。
- 2026-09-13 已停止误用普通 uvicorn 启动的 Windows SAPI 版 8000 服务，并通过 `start_ai_bridge_gpt_sovits.ps1` 重新启动个性化音色版 AI bridge；现场确认 11434、9880、8000 均监听，`/config` 为 `tts_backend=gpt_sovits`、参考音频已配置，`/debug/tts` 实际返回 `status=ok/backend=gpt_sovits`，未回退 SAPI。该运行状态在电脑重启后需按启动指南重新建立。
- 已澄清自定义音色状态：用户自己的参考语音驱动的 GPT-SoVITS 零样本个性化音色已经联调成功；尚未完成的是训练集微调，不影响现有个性化音色。9880 单独启动不会让已运行的普通 uvicorn 自动切换后端，8000 必须通过 `start_ai_bridge_gpt_sovits.ps1` 重新启动并确认 `/config` 为 `tts_backend=gpt_sovits`。
- 新增 `docs/项目指南/项目重启后服务启动指南.md`，统一记录电脑重启后的网络确认、Ollama、GPT-SoVITS、AI bridge 启动顺序，自检命令、ESP32 连接检查和常见故障；并加入 `docs/README.md` 索引。
- 已新增自定义音色 TTS 接入第一版：`server/services/tts_service.py` 支持 `windows_sapi` 与 `gpt_sovits`，GPT-SoVITS 失败时可回退 SAPI；新增 `/debug/tts` 与 `/config` TTS 配置回显。默认仍为 Windows SAPI，尚未训练或配置实际自定义模型。
- 新增 `docs/项目指南/custom_voice_training_and_tts_integration.md`，记录授权、数据准备、训练阶段、API 配置、测试方法和故障判断。
- 已检查用户提供的 `20260907_003026.m4a`：AAC、48 kHz、双声道、约 40.9 秒；新增 `server/tools/convert_reference_audio.py`，可转换为 GPT-SoVITS 使用的 16 kHz 单声道 PCM WAV。
- 已检查新的短参考音频 `20260907_232225.m4a`：AAC、48 kHz、双声道、约 5.14 秒，符合 GPT-SoVITS 零样本推理要求的 3 至 10 秒范围；已在下载目录生成对应的 `20260907_232225_16000hz.wav`（16 kHz、16 bit、单声道），待在推理 WebUI 中试听验证音色。
- 用户已完成零样本 WebUI 试听，生成的 `audio.wav` 为 32 kHz、16 bit、单声道、约 3.34 秒；ASR 可完整识别目标句，用户反馈音色效果可接受。
- 已按当前 GPT-SoVITS `api_v2.py` 修正 TTS 参数名为 `text_lang` / `prompt_lang` 并统一语言代码为 `zh`；新增 v2ProPlus API 配置和两个启动脚本。
- 已完成真实 `/debug/tts` 联调：返回 `status=ok`、`backend=gpt_sovits`，生成约 3.72 秒的 16 kHz、16 bit、单声道 WAV，ASR 可完整识别“我会安静地陪着你，不用着急”；确认未回退到 Windows SAPI。
- 本轮 Python 语法检查与 `platformio run` 均通过；未烧录 ESP32。
- 已读取旧 `Prp` Arduino 舵机工程和项目原始材料清单，确认现有硬件包含 PCA9685、LM2596、TP5100、2S 7.4V 电池及 SG90；旧代码为三路舵机，当前新目标为四脚加尾巴五路。
- 新增 `docs/项目指南/five_servo_hardware_and_evaluation_plan.md`，记录扭矩估算/实测方法、单 ESP32 合并架构、电源与线束小型化方案、语音量化指标及分阶段验收流程。
- 旧舵机工程拟从 `E:\Projects2026\Prp` 重命名为 `E:\Projects2026\Prp_servo_control`；当前目录被其他程序占用，Windows 拒绝重命名，尚未执行成功，也未复制或删除原工程。
- 旧舵机工程已再次通过 `platformio run`；检测到 ESP32-S3 USB 串口为 COM7。工程内工作区文件已改名为 `Prp_servo_control.code-workspace` 并重新提交给 Codex 打开，但根目录仍被后台工作区进程占用，尚不能完成目录改名。
- 新增 `docs/项目指南/servo_bench_wiring.md`，固定单舵机台架使用 `GPIO1=SDA`、`GPIO2=SCL`，明确 PCA9685 `VCC` 接 3V3、`V+` 接外部 5V、所有 GND 共地；实际烧录和动作等待用户完成安全接线确认。
- 单舵机台架首次烧录后发现旧工程未接的触摸输入悬空，连续误触发“害羞”动作；已在旧工程增加 `TOUCH_INPUTS_ENABLED=false`，改为串口专用测试固件，重新编译并成功烧录 COM7。串口帮助命令响应正常且误触发消失，等待重新接通舵机 5V 后发送实际动作命令。
- 用户已完成旧工程的单只 SG90 台架动作测试：舵机正常运动且无尖叫；这只验证了单舵机链路，五路并发、电流和机械负载仍未验证。
- 统一工程已把 PCA9685 通道扩展为 `front_left/front_right/rear_left/rear_right/tail` 五路，主页均为 90°；脚部暂限 70–110°，尾巴暂限 60–120°，均为待机械校准的保守台架值。
- `RobotMotions` 已改为独立 FreeRTOS 动作任务和长度 8 的命令队列；公开动作函数仅入队，五路姿态在动作任务中同步插值，避免阻塞录音、网络和播放调用线程。
- 新增 `motion reset/shy/happy/curious` 与 `servo fl/fr/rl/rr/tail <角度>` 串口命令；必须先执行 `start machine control`，越界角度会被拒绝。机器控制开关现在也约束 AI 动作和本地命令词动作。
- 固件版本更新为 `2026-09-08-five-servo-v1`；`platformio run` 编译成功，RAM 14.8%，Flash 72.1%。
- 经用户明确确认，已把 `2026-09-08-five-servo-v1` 成功烧录到 COM7，写入校验通过并自动复位；串口 `status ai bridge` 已确认新版本运行，Wi-Fi 为 `connected`、AI bridge 为 ready。五路动作尚未发送指令实测。
- v1 上板测试发现：执行 `start machine control` 后，未连接的 GPIO8/9/10 触摸输入悬空，持续误触发动作并占满队列，导致 `servo fl` 指令看似无效。修正版 v2 默认设置 `TOUCH_INPUTS_ENABLED=false`，不初始化或轮询触摸输入；`end machine control` 还会清空待执行动作并请求复位。
- 修正版固件版本为 `2026-09-08-five-servo-v2`；`platformio run` 编译成功，RAM 14.8%，Flash 72.0%。用户确认后已成功烧录 COM7，写入校验通过；串口已确认运行 v2，随后已关闭监视器并释放 COM7，等待复测。
- 用户已实测 v2：`start machine control` 显示 `touch inputs compiled off` 后不再自行循环；`servo fl 80`、`servo fl 100` 均只入队一次且通道 0 运动符合预期。由此确认悬空触摸误触发问题已修复，通道 0 单路命令与动作队列已验证；其余四个通道和组合动作尚未实测。
- 已补充成品脱离 USB 的供电方案：单块 2S 电池经保护、开关和 5V/6A～8A 稳压后，星形分为舵机、ESP32 `5V/VIN` 和音频支路；USB 仅用于烧录调试，并需避免与外部 5V 倒灌。
- 用户提供的“糯糯”角色设定已保存为 `server/prompts/nuonuo_v1.txt`；服务端通过 `PRP_PERSONA_PROMPT_NAME/FILE` 加载独立人设文件，接口新增 `persona`/`reply_persona` 和 `/config` 人设信息，后续可不改业务代码切换多套提示词。
- 糯糯提示词已增加语音长度、自然表达、疗愈边界和负面情绪约束；服务端固定使用已选择的 `cute/encourage` 情境模式，并校正情绪与动作，避免压力/焦虑被错误标记成 `happy`。五类文本调用均走 Ollama 成功，正式主观效果仍待用户测试。
- ASR 默认模型由 `tiny` 升级为 `small`，解码改为 `beam_size=5/best_of=5`、关闭跨片段文本条件，并加入 OpenCC 繁转简；提示词和热词保留可配置但默认关闭，避免短录音幻听。
- 使用四段历史真实录音做非正式对比：`small` 将明显错句改善为更合理文本，热启动单条约 1.6～1.8 秒；因旧样本没有完整人工标准文本，尚不能报告正式 CER。
- 新增 `server/tools/benchmark_asr.py`，可读取 `audio_file,reference` CSV，输出逐条 CER、总 CER、整句正确率与耗时。Python 语法检查、脚本入口和 `platformio run` 均验证通过；本轮未烧录 ESP32。
- 连续对话原来已实现但只有 3 轮、6 秒等待；现改为每次回复结束后继续监听，30 秒无语音才退出，最多 8 轮。固件版本更新为 `2026-09-13-conversation-v1`。
- ESP32 已增加 AI 请求往返与服务器分阶段耗时日志；服务端已增加 ASR/Ollama 启动预热。本机预热约 3.1 秒，预热后的糯糯文本回复约 0.56～1.2 秒。
- 检测到 RTX 4060 Laptop 8GB；`faster-whisper` GPU 测试目前被缺少 `cublas64_12.dll` 阻塞，尚未启用 CUDA，当前继续使用 `small/CPU/int8`。
- 新版后台 AI bridge 已启动在 8000 端口，`/config` 已确认 `persona_prompt_name=nuonuo_v1`、`asr_model_name=small`、模型预热开启；当前 GPT-SoVITS 9880 未运行，因此该后台服务暂用 Windows SAPI。
- 本轮 Python 语法检查和 `platformio run` 均通过；连续对话与新增 ESP32 延迟日志尚未烧录实测。

## 未完成

- 修正版自定义音色模型已完成 SoVITS4轮/GPT5轮训练、权重加载和电脑端合成；用户已试听并反馈高概率重复，质量验收未通过，新权重尚未接入正式机器人。旧v1存在标注错配，不可用作正确训练结果。
- 回复生成已完成第一版风格化改造，但还需要真实交互测试；本地 LLM 默认未强制开启。
- 当前服务是后台隐藏启动，日志写入 `server/uvicorn.out.log` / `server/uvicorn.err.log`；如需实时观察，应前台启动 uvicorn 或用 `Get-Content -Wait` 追日志。
- 动态端点检测已随统一固件上板，阈值仍需基于真实串口日志系统测试；新的“30 秒无操作退出、最多 8 轮”参数尚未烧录。
- ASR 准确率仍需基于新录音样本评估和优化。
- 新人设和 `small` ASR 已由当前 8000 端口后台服务加载，仍需通过 ESP32 真实语音链路做主观与量化测试。
- 连续对话 30 秒等待和 ESP32 分段延迟日志尚未烧录；烧录前需用户确认覆盖当前 v2 固件。

## 下一步

- 用几句文字/录音测试 `cute` 和 `encourage` 风格是否差异明显。
- 重启 AI bridge，通过 `/config` 确认 `persona_prompt_name=nuonuo_v1`、`asr_model_name=small`，再用固定文本评价糯糯的人设一致性。
- 经用户确认后烧录 `2026-09-13-conversation-v1`，实测首次唤醒后连续两轮问答、等待 10 秒后继续说话、30 秒不说话自动退出，并记录各阶段耗时。
- 录制 20～50 条带标准文本的真实测试语料，使用 `benchmark_asr.py` 建立 `tiny` 与 `small` 的 CER、整句正确率和 P50/P90 延迟基线。
- 烧录端点检测固件后测试短句、长句和不开口三种场景，观察串口中的 `Speech detected`、`Endpoint recorder finished`、`reason`、`max_rms`、`max_peak`。
- 再用真实录音建立 ASR 测试集，逐步调整模型、增益、VAD 和降噪。
- 准备参考音频并启动 GPT-SoVITS API，先执行 `/debug/tts` 验证零样本/少样本效果，再决定正式训练参数。
- 在 ESP32 上进行端到端试听，确认动态回复下载与播放正常；之后再根据实际听感决定是否整理 10 至 30 分钟数据进行微调训练。
- 测量整机与肢体质量、舵机力臂和是否承重；先用一只现有 SG90 做机械负载与电流台架测试，再决定微型舵机型号。
- 先执行 `servo fl 90` 和 `motion reset` 完成通道 0 收尾测试；随后断开舵机 5V，依次把同一只舵机换接通道 1–4，分别测试 `fr/rl/rr/tail` 的保守角度，记录实际方向和机械限位。

## 2026-09-15 论文正式版正文排版

- 按用户要求直接修改 `论文初稿/毛绒陪伴机器人语音与动作系统设计_正式版.docx` 的正文格式：五号字、首行两字符、单倍行距、分级标题及官方页边距、页眉页脚距离。原文件备份在 `论文初稿/备份/`。
- 发现此前封面合并误截断中英文摘要，仅留下英文关键词尾部；本次从保留的 `已废弃.docx` 恢复完整摘要和关键词。第1章至致谢的文字未改动。
- 封面所在节、共享样式、印章及图片资源均保持原样；Word 导出前后封面图像逐像素一致。完成9页排版检查，PDF及预览保存在 `论文初稿/排版检查/`。
- 新增 `paper_tools/format_official_paper.py` 和 `paper_tools/check_paper_layout.py` 记录格式处理与核验方法；不涉及固件修改，未编译或烧录ESP32。后续继续审阅论文内容及补充实验依据。

# Agent 工作记忆

本文件记录本项目中需要长期遵守的协作方式和已发生问题的复盘。后续工作前应优先参考。

## 终端命令交付前检查

每次把可复制命令发给用户前，agent必须对最终完整命令块逐项复核，不得只检查被调用脚本。

1. **Shell与执行策略**：本机最新transcript确认VS Code为Windows PowerShell 5.1；不能默认为PowerShell 7，也不能假定当前会话允许.ps1。已审阅的本项目脚本统一用`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "脚本绝对路径"`运行。禁止无依据改回裸`& .\xxx.ps1`；外层`& { ... }`不会放行策略。仅对该子进程生效，不要求用户修改CurrentUser/LocalMachine策略。若组织策略仍阻止，停下报告具体原因。
2. **目录、参数与编码**：代码块自带当前项目Set-Location或完整路径；含空格/中文路径正确引用，区分PowerShell与串口命令。按PS5.1核对语法、脚本文件编码和Python UTF-8输入输出；不假定另一终端的变量、PATH、已激活环境或权限会保留。
3. **固定已验证工具**：PlatformIO只用`C:\Users\ASUS\.platformio\penv\Scripts\python.exe -I -X utf8 -m platformio`（已验证Core6.2.0），不裸调PATH上的platformio。启动器上次打包为Python3.13，已核实入口为`C:\Users\ASUS\scoop\apps\python313\current\python.exe`；打包/包内字节码比对使用相同小版本，并区分生产bridge实际Python与测试/打包Python。缺失先说明，不自动换环境或重装。
4. **失败传播**：每次外部程序（包括子PowerShell）后立即检查`$LASTEXITCODE`并在非零时throw；`$ErrorActionPreference = "Stop"`和Start/Stop-Transcript不证明外部程序成功。任一步失败不得继续依赖它的打包、烧录或验收，不同时跑两套构建。
5. **保留已验证包装**：从历史成功命令改写时，逐项比对保留`-NoProfile -ExecutionPolicy Bypass -File`、专用解释器、隔离/UTF-8参数及错误检查；不能只因重组为一个代码块就删掉这些参数。发出前检索规范中的已知故障，不再让用户验证已经知道会失败的调用方式。
6. **边界与证据**：构建/串口/服务仍在用户可见终端进行，先查服务与串口归属；已有烧录授权保持有效，但舵机断电/机器控制关闭要求不变。只做静态复核必须写明未运行；通过入口不等于功能/硬件PASS。修正失败时给完整替换命令，不要求用户自行拼接参数。

### 执行策略遗漏复盘（2026-09-29）

- 用户执行agent提供的完整代码块时，第一条`& .\tools\verify_roles_launcher.ps1`即被执行策略拒绝（UnauthorizedAccess）。transcript只包含同秒的开始/结束，没有测试、构建或打包结果；不能归因为Python、依赖或固件错误，也不能从“已停止脚本”推断通过。
- 可观察的流程原因：agent已读过采用`powershell -NoProfile -ExecutionPolicy Bypass -File`的项目入口，却在重组交付命令时改成直接调用；复核覆盖了脚本内部Python/Core，没有覆盖外层PowerShell能否启动脚本。现有规范强调可见终端，但缺少执行策略和整块命令的强制检查，修复经验仍依赖临时聊天上下文。
- 责任在agent交付检查遗漏，不要求用户通过反复尝试来发现已知前提。不能把这一流程判断冒充对模型内部记忆机制的确定诊断；可采取的修正是把前提持久化为上方检查表，并在全局/项目AGENTS入口重复提示。
- 已给出子PowerShell临时Bypass并逐步检查退出码的完整替换命令；尚未收到其执行结果，不宣称验证、打包或烧录完成。

## 用户工作偏好

- 需要用户执行命令时，直接在普通聊天里提供可复制的PowerShell代码框，并简述用途和预期结果；不要把长命令放进异步问答卡片。命令末尾不附中文句号，避免复制成参数的一部分。
- 预制演示库的现行需求（2026-09-29澄清）：每行独立定义用户输入A→固定回复B，可配动作；各行没有前后顺序、首句入口或解锁关系。用户自己控制演示情节，设备不预测/要求下一句；不得再引入“下一句编号”、剧情状态机、退出/重开或播放完成后推进剧情的协议。此前严格逐句方案是agent误解且从未实现，已作废。
- 本地项目唯一根目录为`E:\Projects2026\Prp_voice_servo_unified`。原`E:\Projects2026\Prp`迁入`legacy\Prp_servo_arduino`，原`E:\college\毛绒治愈机器人PRP`迁入`archive\PRP_原始项目资料`；旧Git/未提交修改/原资料完整保留，勿把历史文档里的旧绝对路径当现行入口。当前开发用main/server，不混入归档代码。归档含发票与旧独立仓库，暂不整包推送Git。
- 2026-09-15起，每完成一个阶段都要保存到Git：先验证、更新进度和结构地图、检查差异与敏感文件，再提交；本地提交与远程推送必须分开说明。GitHub默认账号`nianchu3110988968`，本项目提交身份`nianchu3110988968 <nianchu3110988968@gmail.com>`，已得到用户确认，不重复询问。具体远程地址/可见性和推送授权以实际配置为准，不把浏览器登录当成Git凭据。
- 已经用户确认创建并配置私有origin：`https://github.com/nianchu3110988968/Prp_voice_servo_unified.git`。后续正常阶段验证后提交并推送该远程，不重复询问账号，不改为公开、不强推；推送失败如实记录。模型/录音/真实网络配置及项目外GPT-SoVITS不在Git备份范围。
- manbo当前唯一数据目录：`E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo`。实验名`manbo`，启动器`server\tools\start_manbo_training.ps1`预填9874；由0d按需开9871。旧manbo素材/权重已在2026-09-15经用户授权移入回收站；新实验未训练。不要再用历史相似命名目录。保存当前`clips.list`时同步`full_text.txt`；只有此启动器派生的校对服务带有同步环境变量。
- 2026-09-15起，GPT-SoVITS训练、校对、推理及人声分离的所有网页操作只在用户自己的外部浏览器进行，禁止在Codex内置浏览器操作。外部浏览器控制不可用时明确说明并由用户手动执行，不自动开内置页面补位；只保留必要入口，说明端口对应的用途。同一个localhost端口是同一个服务，浏览器中的输入状态不一定共享，旧校对服务还存在全局页码风险。
- 给出任何本地链接/媒体预览时，除链接外必须同时写出可复制的完整绝对路径及用途；遵循全局 `local-path-handoff` 技能。训练数据采用唯一当前入口，不再让用户在多个相似命名目录中猜选。
- 用户本轮授权清理无关/旧manbo素材、缓存、试听和模型，保留唯一当前中文切片/标注、连续中文音频/整段文字及必要依赖，保护三月七、官方底模、个人声音配置。完成清理后不得再把历史记录中的旧manbo路径当作有效输入；清理记录保留在文档中，便于追溯。
- 每次修改代码后，必须说明改动发生在哪个文件、哪个位置，以及哪些代码是核心实现。
- 每次修改代码后，必须运行 `platformio run` 验证，除非明确说明不能运行。
- 不要直接烧录 ESP32，除非用户明确要求或确认。因为板子上可能有可用固件。
- 论文和代码叙述都必须忠实于已有证据，不把未实现功能写成已完成。
- 后续项目目标是模块尽可能解耦，先从语音模块拆最小原型开始。
- 指令、操作方法和临时约定需要沉淀到文档，避免后续遗忘。
- 讨论成品供电时必须明确 ESP32 脱离 USB 后的供电路径，并区分“单块电池”“单路稳压”和“所有负载共用同一条布线”；不能默认 USB 继续供电。
- 每次完成阶段性任务后，必须更新 `docs/工作留档/task_progress.md`，用简短语言记录已完成、未完成和下一步，方便切换 agent 后继续工作。
- 新建重要文档、增加功能模块、调整入口文件或改变运行链路时，必须同步更新 `docs/项目指南/project_structure_map.md`，把新增文件和职责纳入项目结构地图。
- 每次完成任务后，必须先说明当前工作进度：已经完成到哪一步、用户应该怎样测试、预期会看到或听到什么表现；不要只说“完成了”。
- 后续如果修改 ESP32 AI bridge 录音端点检测逻辑、阈值、缓冲策略或上传行为，必须同步更新 `docs/项目指南/recording_endpoint_detection.md`。

## 已发生问题与复盘

### GPT-SoVITS 校对页跨窗口串页覆盖（2026-09-14）

- 本机`tools/subfix_webui.py`用全局`g_index`作为Submit Text的写入位置，所有浏览器共享；另一窗口加载第0页，会影响留在第10页的窗口提交。不是用户只漏按保存，也不是输入框显示问题。
- 不得在用户校对时另开或刷新同一校对服务的页面。当前未实现会话隔离，必须单窗口操作；只读AX/DOM采样不触发翻页，但新开页面本身可能改变全局索引。
- 事故发生时先保留所有可见未提交文本和磁盘备份，不能先刷新/提交；恢复后必须使旧进程内存及旧窗口失效，防止再次写回。
- 格式化前不能只查条数和文件名，还应检查音频与文本对齐、跨页重复。首次10条文本被第二页覆盖时，39条计数仍完全正常。
- 本次从内置浏览器保留的第一页、历史输出和凌晨整段稿恢复索引0～9；保留10～38的新修订。旧manbo训练缓存及权重均受影响，修复标注后要新实验重建，不可宣称旧模型已经修好。

### 测试进度总结误判

现象：

- 用户完成第一轮语音交互测试后询问当前进度，回复仍按旧的烧录失败/ASR 空文本状态总结，忽略了测试后新生成的录音与识别结果。

原因：

- 没有在总结前重新检查最新测试产物、服务端录音时间戳和可用日志。
- 把上一轮对话中的已知问题当成了当前状态，未区分“历史问题”和“最新测试结果”。

修正：

- 后续凡是用户说已经测试、已经执行、刚刚跑过时，必须先检查最新文件时间戳、日志输出或用户贴出的最新结果，再做进度判断。
- 如果本地可见 `server/recordings`，优先按 `LastWriteTime` 找最新 WAV/PCM，并用测试脚本验证 ASR/回复结果。
- 汇报时明确区分“已经实现并验证”“部分成功”“待完善”，不把过期故障当成当前结论。

后续避免：

- 回答测试进度类问题前，先问自己：有没有新日志、新录音、新构建输出需要重新读取？
- 如果没有看到用户提到的日志，先说明“我需要查看最新日志/产物”，不要直接沿用旧结论。

### 触摸输入刷屏

现象：

- 只接语音模块、未接触摸和舵机时，串口持续输出 Touch 1/2/3 和 PCA9685 not ready 相关日志。

原因：

- 触摸 GPIO8/9/10 未接入时处于悬空状态，被轮询逻辑误判为触摸上升沿。
- 初版只关闭了机器日志，但没有提供单独的机器控制入口开关。

修正：

- 增加 `machine_control_enabled`，默认关闭触摸/舵机控制入口。
- 增加 `start machine control` 和 `end machine control` 串口指令。
- 未知串口输入改为静默忽略，避免键盘输入被反复打印。

后续避免：

- 新增硬件模块时，默认应支持单模块测试模式。
- 未接硬件的输入引脚不能默认驱动核心动作。
- 串口命令应使用白名单，未知输入不要刷屏。

## AI Bridge Direction

- Prefer ESP32-S3 as the local wake/body/audio front-end and a computer server for ASR, LLM response generation, and personalized TTS.
- Keep Wi-Fi and server settings isolated in `main/network_config.h`; do not hard-code user credentials into logic files.
- Preserve local fallback behavior when the computer server is unavailable so the voice module remains testable.
- First network milestone: wake word -> record short PCM -> HTTP POST to computer -> parse JSON reply -> dispatch motion intent.
- Project-facing plans, test guides, and operation documents should be written in Chinese by default, unless the user explicitly asks otherwise.
- When network behavior is unclear, add explicit runtime diagnostics instead of relying on silent fallback. The user needs visible proof of firmware version, Wi-Fi state, and server URL in serial logs.
- ESP-IDF Wi-Fi requires an NVS partition. If `wifi_manager_start()` returns `ESP_ERR_NOT_FOUND`, check `partitions.csv` before debugging SSID/password.

## Code Editing Reflection

- When moving duplicate code blocks, make the new block syntactically unique before deleting the old one. Identical snippets can cause `apply_patch` to remove the wrong occurrence.

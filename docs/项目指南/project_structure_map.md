# 项目结构地图

## 2026-10-09 桃金娘音色首轮训练准备（本机素材，不入 Git）

- `C:\Users\ASUS\Downloads\PRP_410582114\semantic_v3\training.list`：用户确认文字后生成的 34 段、199.55 秒正式首轮训练输入；4 段短于 3 秒的 WAV 保留但未入清单。
- 同目录 `training_manifest.json`、`full_text.txt`、`TRAINING_START.md`：清单哈希与排除依据、连续文字和 v2ProPlus 网页启动/格式化/训练顺序。
- `C:\Users\ASUS\Downloads\PRP_410582114\inspection\start_myrtle_training.ps1`：仅在用户可见 VS Code PowerShell 中启动 9874 训练主页，预填 `myrtle_zh_v1` 与本批素材；不自动格式化或训练。训练网页只能由用户自己的外部浏览器操作。

## 2026-10-08 答辩交互流程图

- `docs/答辩材料/README.md`：图片用途、讲解词及验证边界。
- `docs/答辩材料/项目交互流程图.png`、同名`.svg`：16:9普通对话流程图；区分机器人与电脑职责、回复语音与动作指令，标注整机动作联动待验证。

## 2026-09-30 诊断增量（离线回归/构建通过，服务待重载）

- `server/ai_bridge_server.py`：语音请求打印词库分支原因；本机维护`POST /debug/phrase-match`复用当前语义匹配/缓存，只返回诊断，不进行ASR/TTS或硬件动作。
- `server/services/dialogue_service.py`：最近4轮历史保留，增加120秒闲置过期；不等价于设备会话隔离。
- `server/tests/test_dialogue_diagnostics.py`：历史生命周期、诊断分支和本机维护访问控制回归。验证/上线状态见task_progress。

最后核对日期：2026-09-29


最后核对日期：2026-09-29

本文是项目目录与关键文件职责的维护入口。后续新建文档、增加功能模块、调整入口文件或改变运行链路时，必须同步更新本文，避免后续交接时只依赖过期 README 或口头记忆。

原始截图快照：

```text
docs/assets/project_structure_map_snapshot_20260915.png
```

## 维护约定

- 本 Markdown 是后续维护的权威版本；截图只作为 2026-09-15 的视觉快照。
- 新增 `main/`、`server/`、`docs/`、`tools/` 等目录下的重要文件后，应补入本图。
- 新增功能时，不只写文件名，还要写一句它在链路中的职责。
- 如果某文件只是旧示例、占位、调试脚本或历史产物，需要明确标注，不能写成当前正式入口。
- 如果根目录 README 与当前源码冲突，以当前源码、`docs/README.md` 和 `docs/工作留档/task_progress.md` 为准。

## 2026-09-29 多角色与桌面启动器（离线测试/编译及exe打包烟测通过，真实联调待验证）

本次EXE复核修复已由用户在VS Code运行验证脚本并成功返回；新包7模块源码比对与真实Tk窗口PASS，真实模型/硬件仍待测：

- `server/services/bridge_identity.py`：记录bridge启动时的项目目录、业务源码摘要、功能协议和实际Python/PID；启动器对照磁盘，拒绝复用旧实例/其他目录/其他解释器，不按端口杀进程。提示词/动作JSON不纳入代码摘要，其既有动态/显式加载规则保持。
- `server/tests/test_bridge_identity.py`：旧API、源码变化、跨目录/解释器和正确服务复用的离线回归；不连接硬件或模型。
- `tools/inspect_launcher.py`：读取EXE内部代码对象并与源码比较，忽略PyInstaller改写的文件名；要求使用同Python小版本。`build_launcher.ps1`在包比对通过后进行真实Tk烟测，不启动服务。
- `verify_roles_launcher.ps1`的固件步骤固定专用penv Core隔离调用；它和打包脚本的`-Python`参数仅指定测试/打包解释器，不改变PlatformIO Core或生产本地配置。

- `server/personas/New_ManBoo.example.json`及同名本地档案：曼波人格名称和正文入口；`server/roles/`保留组合预设及旧角色兼容，本地JSON不提交。9月29日New_ManBoo名称统一为“曼波”，权重/参考组合不变。
- `server/services/role_config.py`：字段/ID/路径/UTF-8提示词/权重对SHA256验证；不反序列化或训练模型。
- `server/services/role_runtime.py`：当前角色、成对热切换、失败回滚与主TTS隔离、历史清空；交互/TTS/预制生成共享事务锁。
- `server/prompts/New_ManBoo.txt`：曼波专属抽象/搞怪人格，9月29日已改写并静态核验，尚未加载或真实试听；保留历史nuonuo_v1.txt。`dialogue_service.py`仍叠加通用边界、cute/encourage风格及JSON协议，按用户要求留待后续处理。
- `tts_service.py`动态读取当前参考参数；`phrase_library.py`按角色ID/配置摘要隔离目录，参考内容参与指纹；旧缓存保留，不自动批量合成。
- `ai_bridge_server.py`提供本机维护头保护的角色接口、预热/实际TTS状态，旧角色后台任务在切换后取消，响应协议继续兼容ESP32。
- `server/launcher_core.py`：标准库服务监督器、11434/9880/8000健康复用、顺序就绪检查、仅停止持有句柄的自有进程，PID记录只作审计。
- `server/launcher_app.py`：Tkinter角色选择、完整启动、仅切换、健康检查、停止与持续日志；配置在外部项目中，打包不带模型/录音。
- `server/configs/launcher.example.json`：运行时安装位置模板；本地 `launcher.local.json` 不提交。`server/.runtime/` 保存派生YAML/PID记录，不是手工配置源。
- `server/tools/role_service.py`：可见终端前台启动兼容入口；原两份PowerShell启动脚本保留并委托此入口。旧手写GPT-SoVITS YAML保留，不参与新入口启动。
- `server/tests/test_roles_launcher.py`：临时文件/模拟HTTP与进程的配置、回滚、身份、缓存和归属测试；`tools/verify_roles_launcher.ps1`在用户可见终端串联服务端测试与platformio run。
- `tools/build_launcher.ps1`：PyInstaller构建并打开真实Tk窗口检查退出；不自动启动模型服务。测试/打包/真实联调/硬件状态以进度记录为准。

## 2026-09-29 独立预制对话与起播动作（离线回归/固件构建通过，未烧录实测）

- `docs/项目指南/phrase_library_demo.md`：每行独立A→B，可乱序/重复触发，沿用两列词库并支持可选动作；不引入下一句编号、剧情进度或推进确认接口。用户工作簿不由程序覆盖。
- `docs/项目指南/voice_motion_selection.md`：模型选动作的阶段、中文规则/目录维护、起播事件、安全与验证入口。
- `server/services/motion_policy.py`、`server/prompts/motion_selection.txt`、`server/configs/motion_catalog.json`：动态读取选择规则、动作说明/启用项，只允许固件既有ID；无效配置/模型动作退none。`dialogue_service.py`不再用关键词覆盖模型动作，风格约束保持。
- `server/services/phrase_library.py`：首表只读可选动作、相同回复不同动作的独立ID和音频复用；同一次真实Ollama请求匹配词条并选择动作，固定动作优先。
- `main/audio_playback_gate.h`、`bsp_board.cc`、`audio_reply_player.cc`：统一播放占用/准备后起播回调，保留DMA排空和数字静音；WAV格式不符或播放准备失败不触发动作。
- `main/robot_motions.cc::tryStartVoiceMotion`：起播点非阻塞准入，仅整机控制开启且动作空闲时接受，首写超过40ms拒绝迟到动作；15/11/7/3/0通道、限位和单路隔离保持。
- `server/tests/test_phrase_motion.py`与既有音频/舵机主机测试：独立词条、动作配置、同调用选择、起播顺序、失败/忙碌/过期隔离；`tools/verify_servo_channels.ps1`串联离线测试、platformio run和主机测试，不烧录/启动服务。
- `tools/verify_voice_logging.ps1`：上述验证链的固件构建步骤固定使用用户目录`.platformio/penv/Scripts/python.exe`，以隔离模式运行`-m platformio`并打印入口/版本；不再使用PATH上的另一套Core，缺失时停止。用户复跑确认Core6.2.0与156.66s固件构建成功，词库/日志及trace/音频起播/舵机主机回归通过；预期故障注入日志不代表服务失败，细节见进度记录。未烧录或真实模型/硬件验收。

## 当前目录地图

2026-09-28～29 自定义通道与尾部单路调试（源码`2026-09-28-servo-map-v1`；9月29日编译/离线回归PASS、COM7烧录成功，串口版本与完整欢迎音已确认；舵机未实测）：

- `main/robot_config.h::SERVO_CHANNELS`：唯一五部位通道配置，fl/fr/rl/rr/tail=15/11/7/3/0；编译期范围/重复检查，动作数组仍按部位顺序。
- `main/pca9685_controller.h/.cc`：逐通道使能掩码；恢复缓存脉宽时也保持非选中通道FULL OFF，不让旧会话残留值重新使能腿部。
- `main/robot_motions.h/.cc`：单路home使能、home±5°边界、其他部位/组合动作拒绝、会话代次隔离；写入失败停止并尝试关PWM。
- `main/main.cc`：串口`start servo debug <name>`和`end servo debug`，保持语音/AI/触摸动作入口关闭，与整机模式互斥；语音日志/模型链路不变。
- `tests/firmware/servo_channels_test.cc`、`tests/servo_stubs/`：真实驱动/动作层的I2C寄存器广播和队列/延时模拟，不是实物或真实RTOS并发验证。
- `tools/verify_servo_channels.ps1`：在VS Code可见终端串联既有词库/日志/固件编译与新增舵机主机测试，不烧录、不开串口/服务。
- `docs/项目指南/servo_channel_setup.md`：当前接线、尾部测试门槛、已安装舵盘/无万用表/200g真实行走目标的限制；尚未实现新坐下/前进动作或机械零位校准。

2026-09-22 Excel词库/缓存先播（源码`2026-09-22-phrase-cache-v1`，离线验证通过、未烧录）：

- `docs/响应词对话/响应词对话1.xlsx`：用户维护的唯一当前词库输入，首张表两列示例输入/标准输出；本轮只读，不覆盖未保存编辑。
- `server/services/phrase_library.py`：只读XLSX校验、Ollama语义分类、音色/文件指纹、WAV校验和原子缓存发布；`server/phrase_cache/`为Git忽略的生成音频/清单。
- `server/services/phrase_jobs.py`：有界后台任务和结果期限；`server/ai_bridge_server.py`增加能力协商、缓存首包、后台TTS结果、预制音频GET和本机维护接口；模型调用不占用事件循环。
- `server/tools/prepare_phrase_library.py`：用户在可见VS Code终端调用已运行8000生成缓存，沿用该服务的实际TTS配置，不启动服务或切换权重。
- `main/phrase_background.h/.cc`：后台名额、取结果/日志、真实下载后丢弃；`main/ai_client.h/.cc`扩展协议与堆上8KB JSON缓冲；`main/audio_reply_player.h/.cc`新增只下载不播放路径；`main/voice_trace.h/.cc`区分缓存/后台，正常日志格式不变。
- `tools/verify_phrase_cache.ps1`、`server/tests/test_phrase_library.py`、`tests/firmware/audio_download_test.cc`与新增HTTP/内存/错误测试桩：离线词库/后台协议回归、platformio run、真实下载代码不播放验证。扩展原trace主机回归；脚本由用户在VS Code执行，当前结果见进度记录。
- URL回归补充：音频下载和后台结果查询都固定同一个服务器URL指针，避免字符串宏展开后的跨数组指针相减；音频主机测试使用MSVC C++20与`/Od /GF-`，验证不合并常量时仍正确拼接，覆盖斜杠、绝对URL和容量边界。
- `verify_phrase_cache.ps1 -OutputCheck`：单独检查PS5下UTF-8双流解码和非零退出码，不编译或请求服务；功能18项+原日志9项、固件与两项主机测试，以及编码/退出码短测均已通过，细节见进度记录。
- `docs/项目指南/phrase_library_demo.md`：Excel规则、单独维护入口、旧固件兼容、命中/失败路径和真实计时定义。不得用缓存播放时间冒充完整实时TTS链路。

2026-09-22 中文演示日志（更新下方历史日志说明）：

- `main/voice_trace.cc`：复用原单调时钟与上传透明观测，将事件合并为中文起止/耗时/结果；不改传输调用。
- `main/ai_client.h/.cc`：同请求ID关联、7项timings_ms解析，补读现有LLM/TTS状态用于回退警告，不增加响应协议字段。
- `main/main.cc`、`main/audio_recorder.cc`、`main/audio_reply_player.cc`、`main/bsp_board.cc`：删除重复成功debug，保留录音能量统计、一次识别/回复、下载/播放边界及错误。
- `server/services/latency_trace.py`、`server/ai_bridge_server.py`：每轮6行中文摘要，同ID且直接使用响应timings_ms；另报失败/回退，保留原录音、API和模型行为。
- `tools/verify_voice_logging.ps1`：用户在VS Code空闲PowerShell运行的验证入口，依次做服务端9项离线测试、platformio run、MSVC主机观测回归；不启动服务、不烧录。
- `server/tests/test_latency_trace.py`、`tests/firmware/voice_trace_test.cc`与`tests/firmware_stubs/esp_log.h`：测试紧凑中文日志、时间字段、回退、控制字符/坏控制台、传输透传和失败边界。
- `docs/项目指南/voice_latency_logging.md`：新旧日志对照与“字幕by索兰娅”排查；`recording_endpoint_detection.md`同步新输出。用户已贴回三项验证通过；本轮未烧录，未重启正在运行的服务。

2026-09-15 本地目录集中（已实际迁移，现行根目录未改名）：

- `E:\Projects2026\Prp_voice_servo_unified\项目入口.md`：现行代码/论文/素材与旧资料的唯一导航。
- `E:\Projects2026\Prp_voice_servo_unified\PRP.code-workspace`：只打开当前根目录的VS Code入口。
- `E:\Projects2026\Prp_voice_servo_unified\legacy\Prp_servo_arduino`：原`E:\Projects2026\Prp`，182文件，保留旧Git与未提交状态；历史工程，不与main源码合并。
- `E:\Projects2026\Prp_voice_servo_unified\archive\PRP_原始项目资料`：原`E:\college\毛绒治愈机器人PRP`，1046文件，保留原PPT/调研/发票/旧语音源码/固件备份。
- `E:\Projects2026\Prp_voice_servo_unified\tools\consolidate_project_folders.ps1`：已执行的一次性安全迁移与断点续迁工具，需PowerShell7；不要当日常启动脚本或重复执行。
- `E:\Projects2026\Prp_voice_servo_unified\.local_migration\20260915\files.json`：本地逐文件SHA256审计。legacy/archive/审计目录不推送Git，当前私有仓库保存整理工具和目录说明；不等于归档资料已做云备份。
- 原两个顶层目录已移除；当前main/server/voice_data/论文初稿保持原位。外部GPT-SoVITS安装仍在E:\AI下，未迁移。

2026-09-15 分段延迟与Git新增（均在 `E:\Projects2026\Prp_voice_servo_unified`）：

- `main\voice_trace.h/.cc`：单轮请求ID、单调时钟事件与汇总、任务隔离的上传写入观察；由`main\CMakeLists.txt`连接transport write包装。
- `main\main.cc`、`main\ai_client.h/.cc`、`main\audio_reply_player.h/.cc`：录音、HTTP/JSON、下载和播放链路传递trace上下文；不调整现有功能流程。
- `server\services\latency_trace.py`：结构化服务端请求日志；`server\ai_bridge_server.py`附加请求头回显和预处理/整请求timings。
- `server\tests\test_latency_trace.py`、`tests\firmware\voice_trace_test.cc`与`tests\firmware_stubs`：服务端离线回归、真实固件观测代码的主机模拟测试。
- `docs\项目指南\voice_latency_logging.md`：阶段定义、对齐方法、采集命令与实测限制。
- 根`AGENTS.md`：阶段验证与Git提交规范；`.gitignore`排除隐私/大文件/生成物；`main\network_config.example.h`为可提交网络配置模板，真实`network_config.h`保持本地不入库。

2026-09-15 manbo整理新增入口（下方旧素材说明若不一致，以本节为准）：

- `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo`：唯一当前39段切片、`clips.list`、连续音频`full_audio.wav`、整段稿`full_text.txt`；`dataset.json`溯源，`README.md`使用说明。
- `E:\Projects2026\Prp_voice_servo_unified\server\tools\start_manbo_training.ps1`：启动预填数据的9874主界面，不自动开浏览器或训练。
- `E:\Projects2026\Prp_voice_servo_unified\server\tools\consolidate_manbo_dataset.py`：已执行的一次性迁移工具；拒绝覆盖现有数据，不再当常规启动工具。
- `E:\Projects2026\Prp_voice_servo_unified\server\tools\cleanup_manbo_legacy.ps1`：已执行的一次性回收站清理工具，不重复执行。
- `E:\Projects2026\Prp_voice_servo_unified\server\tests\test_manbo_workspace.py`：数据哈希/文本对应和隔离保存同步回归测试。
- `E:\Projects2026\Prp_voice_servo_unified\docs\工作留档\manbo_cleanup_20260915.json`：53项回收清单；历史文件不再是有效训练输入。
- GPT-SoVITS安装在 `E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604`，本地`webui.py`支持项目环境变量预填；`tools\subfix_webui.py`保存当前标注时同步整段稿。必要代码回退副本保留。

```text
E:/Projects2026/Prp_voice_servo_unified
├─ main/                                  ESP32 固件源码
│  ├─ main.cc                             启动入口、唤醒/命令/AI bridge 主流程
│  ├─ bsp_board.cc/.h                     INMP441 麦克风与 MAX98357A 喇叭 I2S 输入输出
│  ├─ audio_recorder.cc/.h                固定录音与端点检测录音
│  ├─ ai_client.cc/.h                     HTTP POST 上传 PCM，解析 JSON
│  ├─ audio_reply_player.cc/.h            下载 WAV，取 data 段并播放
│  ├─ wifi_manager.cc/.h                  Wi-Fi 连接与状态
│  ├─ network_config.h                    Wi-Fi、AI bridge、录音和连续对话配置
│  ├─ robot_config.h                      五舵机通道、限位、触摸开关
│  ├─ pca9685_controller.cc/.h            I2C 控制 PCA9685 输出 PWM
│  ├─ robot_motions.cc/.h                 FreeRTOS 动作任务与动作队列
│  ├─ touch_inputs.cc/.h                  触摸输入；当前默认关闭
│  ├─ servo_controller.cc/.h              早期舵机控制封装，当前主动作层不优先依赖
│  └─ mock_voices/                        本地欢迎/开灯/关灯/拜拜提示音
│
├─ server/                                电脑端 AI bridge
│  ├─ ai_bridge_server.py                 FastAPI 主服务，提供 /voice/interact
│  ├─ server_config.py                    ASR/LLM/TTS/persona 配置
│  ├─ services/
│  │  ├─ asr_service.py                   faster-whisper ASR
│  │  ├─ dialogue_service.py              糯糯人设、Ollama、短期上下文
│  │  ├─ tts_service.py                   Windows SAPI / GPT-SoVITS TTS
│  │  └─ audio_utils.py                   PCM 统计与归一化
│  ├─ prompts/nuonuo_v1.txt               糯糯角色设定
│  ├─ configs/gpt_sovits_v2proplus.yaml   GPT-SoVITS v2ProPlus 启动配置
│  ├─ tools/                              ASR测试、音频转换、GPT-SoVITS启动/训练辅助脚本
│  ├─ voice_models/                       参考音频
│  └─ recordings/                         ESP32录音、回复音频和试听产物
│
├─ docs/                                  项目指南、规范、进度留档
│  ├─ README.md                           文档索引
│  ├─ assets/                             图片快照等文档资源
│  ├─ 项目指南/project_structure_map.md   本文件；项目结构地图
│  ├─ 项目指南/voice_module_chain.md      语音模块链路与解耦草案
│  ├─ 项目指南/ai_bridge_plan.md          AI bridge 方案
│  ├─ 项目指南/recording_endpoint_detection.md 录音端点检测说明
│  ├─ 项目指南/voice_ai_optimization_plan.md   语音 AI 优化方案
│  ├─ 项目指南/five_servo_hardware_and_evaluation_plan.md 五舵机与评估计划
│  ├─ 工作规范/agent_working_memory.md    长期协作规则与问题复盘
│  └─ 工作留档/task_progress.md           阶段进度和验证状态
│
├─ boards/                                PlatformIO 板卡配置
├─ managed_components/                    ESP-SR / DSP 依赖组件
├─ tools/                                 项目外部辅助工具和说明图
├─ voiceTest/                             早期录音测试素材
├─ release/                               发布/预编译产物
├─ paper_tools/                           论文文档处理脚本
│  ├─ format_official_paper.py            正式论文正文排版
│  ├─ check_paper_layout.py               论文结构与排版检查
│  ├─ refresh_paper_figures.py            重绘三张核心示意图并替换DOCX内嵌图片
│  └─ refine_paper_language.py             精简开发过程并统一论文状态表述
├─ 论文初稿/                              论文文档、示意图与排版检查产物
├─ platformio.ini                         ESP-IDF + PlatformIO 构建配置
├─ partitions.csv                         Flash 分区；含 NVS、factory、model
└─ README.md                              旧示例 README，部分内容已过时
```

## 当前入口文件

- ESP32 固件入口：`main/main.cc` 的 `app_main()`。
- 电脑服务器入口：`server/ai_bridge_server.py` 的 FastAPI `app`。
- ESP32 构建入口：`platformio.ini`，`src_dir = main`。
- 服务器常用启动脚本：
  - `server/tools/start_ai_bridge_gpt_sovits.ps1`
  - `server/tools/start_gpt_sovits_api.ps1`

## 当前状态提醒

- `README.md` 仍含早期单舵机 GPIO18 示例，不应作为当前五舵机结构依据。
- 板上最近确认版本`2026-09-28-servo-map-v1`包含已有词库/URL修正和舵机安全依赖；9月29日用户在VS Code完成词库/日志、trace/音频/舵机主机回归及platformio run（114.95s，RAM48,640=14.8%、Flash1,479,531=72.2%），均PASS。随后经授权在COM7烧录成功（31.25s，应用写入1,479,936字节，Hash校验通过并RTS复位）；串口已确认该版本、Wi-Fi connected、关闭PWM成功，用户确认本地“Hi朋友”完整播放，且明确本次舵机外部电源已断开。该条件下音频基线通过，舵机通电/运动与音频共存未验收；历史无声的具体电气根因仍未逐项定位。后续phrase-motion-v1仅完成离线回归和编译，尚未烧录。
- 舵机部分最近一次硬件实测仍为 `2026-09-08-five-servo-v2` 阶段：通道 0 的 `servo fl 80/100` 已验证，其余四路与组合动作未系统实测；后来固件保留这些代码，但未重新做舵机回归测试。
- 服务器端 ASR、Ollama、TTS 链路已实现；实际运行状态需要每次测试前重新检查端口、日志和 `/config`。

## 2026-09-22 机械骨架V0（试装版）

- `硬件参数/`：用户提供的尺寸图片；打印服务截图含账户界面，仅留本地。
- `mechanical/v0/硬件尺寸与孔位核对.md`：硬件/孔位台账，区分图示值与预留值。
- `mechanical/v0/generate_frame.py`：独立CadQuery几何生成、STL与干涉检查、渲染；不连接固件或服务端。
- `mechanical/v0/README.md`：装配、标准件、PLA打印和待实测验收；`source_images.json`记录图片哈希。
- `mechanical/v0/output/PRP_V0_with_hardware.SLDASM`：已在SolidWorks保存的STEP导入装配，依赖同目录STEP；不是原生草图建模或已建立运动配合的装配。
- `mechanical/v0/output/PRP_V0_with_hardware.step`及`PRP_V0_frame_only.step`：含硬件包络/仅打印结构的装配评审。
- `mechanical/v0/output/step_parts/`、`stl_parts/`：32个分件；`stl_trial/`：5种优先试装样件。
- `mechanical/v0/output/validation.json`、`assembly_preview.png`：几何验证和真实模型预览；无承重/热/疲劳实测。

## 2026-09-22 硬件草模独立交付（替代当前骨架设计任务）

- `mechanical/硬件草模/`：七种硬件独立 STEP、八种硬件展示总览、使用说明和提取核验；坐标已归一。
- `mechanical/硬件草模/占位_未定尺寸/`：INMP441 20×20×10 暂定占位，不能当作真实尺寸。
- 用户因尺寸与连接复杂度不接受 V0，改为自行设计骨架；`mechanical/v0/` 保留作历史及尺寸证据，不再是当前实施方案。

## 2026-09-29 独立人格、音色与项目控制台

- server/services/profile_config.py：人格/音色解析、自动SHA256、导入、旧角色兼容迁移；roles为可选组合预设。
- server/personas/*.example.json、server/voices/*.example.json：可提交字段示例；同目录.local.json忽略。
- server/launcher_app.py：独立选择、实际状态、交互测试、串口与训练页面；追加日志不自动滚动。
- server/launcher_imports.py：UTF-8人格及权重/WAV导入表单。
- server/launcher_console.py：日志路由、按日期/容量分段持久化、独占串口。
- server/logs/launcher/：本机运行日志（忽略，不自动删除）；server/prompts/导入正文忽略，既有版本化提示词保留。
- server/tests/test_profiles_console.py：拆分配置、切换/回滚、缓存隔离、轮转和串口模拟。
- tools/verify_roles_launcher.ps1：离线测试、源码Tk烟测、PIO编译；tools/build_launcher.ps1：EXE构建及开关烟测。

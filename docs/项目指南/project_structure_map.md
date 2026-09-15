# 项目结构地图

最后核对日期：2026-09-15

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

## 当前目录地图

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
├─ 论文初稿/                              论文文档与排版检查产物
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
- 当前源码固件版本为 `2026-09-13-conversation-v1`，连续对话代码已编译，但根据进度留档尚未烧录实测。
- 已实测板上固件为 `2026-09-08-five-servo-v2`：通道 0 的 `servo fl 80/100` 已验证，其余四路与组合动作未系统实测。
- 服务器端 ASR、Ollama、TTS 链路已实现；实际运行状态需要每次测试前重新检查端口、日志和 `/config`。

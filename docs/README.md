# PRP 项目文档索引

本目录按用途分为三类，后续新增文档优先放入对应文件夹。

本地统一目录导航：`E:\Projects2026\Prp_voice_servo_unified\项目入口.md`。原Projects2026/Prp与college资料已分别归档到本根目录下的legacy与archive；历史文档旧绝对路径仅用于追溯，不能作为现行入口。

## 项目指南

- `项目指南/voice_latency_logging.md`：ESP32录音/上传/JSON/下载/播放时间点、服务端timings_ms、同请求编号关联、测量边界和采集命令。
- 当前 manbo 唯一数据与校对入口：`E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo\README.md`；旧manbo素材/权重路径已失效，训练网页只在用户外部浏览器操作。
- `项目指南/ai_bridge_plan.md`：AI 电脑服务器桥接方案。
- `项目指南/AI桥接测试步骤.md`：AI bridge 手把手测试步骤。
- `项目指南/project_structure_map.md`：项目目录结构地图；新增文档或功能模块后需要同步维护。
- `项目指南/voice_module_chain.md`：语音模块链路与解耦草案。
- `项目指南/voice_ai_optimization_plan.md`：语音 AI 链路优化方案。
- `项目指南/recording_endpoint_detection.md`：AI bridge 录音端点检测模块说明。
- `项目指南/command_guide.md`：串口指令与语音口令指南。
- `项目指南/powershell_commands.md`：常用 PowerShell 命令记录。
- `项目指南/custom_voice_training_and_tts_integration.md`：自定义音色训练与 GPT-SoVITS 接入说明。
- `项目指南/GPT-SoVITS网页训练教学.md`：manbo 中文旁白训练的逐页字段说明、内部原理、今晚快速试听参数、产物路径与续训注意事项。
- `项目指南/项目重启后服务启动指南.md`：电脑重启后依次启动 Ollama、GPT-SoVITS、AI bridge 并完成自检的简明步骤。
- `项目指南/five_servo_hardware_and_evaluation_plan.md`：四脚加尾巴五舵机、单 ESP32 集成、供电布线与论文量化指标计划。
- `项目指南/servo_bench_wiring.md`：PCA9685、ESP32-S3、外部 5V 电源和单只 SG90 的固定接线及台架测试步骤。

## 工作规范

- `工作规范/agent_working_memory.md`：长期协作规则、用户偏好和问题复盘。

## 工作留档

- `工作留档/task_progress.md`：每次阶段任务完成后的简要进度记录。

## 机械骨架与打印

- `../mechanical/v0/README.md`：PLA五舵机骨架V0、安装顺序、标准件、打印小样与承重验证边界。
- `../mechanical/v0/硬件尺寸与孔位核对.md`：商品图片尺寸证据、孔位、SKU冲突和待实测项。

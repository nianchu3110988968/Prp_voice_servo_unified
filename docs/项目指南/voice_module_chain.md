# 语音模块工作链路与解耦草案

## 当前链路总览

当前语音模块是一个本地离线命令词识别链路，不是联网大模型对话链路。

数据流为：

1. 用户说话。
2. INMP441 麦克风把声音转换为 I2S 数字音频流。
3. `bsp_board.cc` 通过 ESP-IDF I2S RX 读取音频帧。
4. `main.cc` 把音频帧送入 WakeNet9 检测“你好小智”。
5. 唤醒成功后，`main.cc` 播放欢迎音频，并切换到命令词识别状态。
6. `main.cc` 把后续音频帧送入 MultiNet7 中文命令词模型。
7. MultiNet 返回命令 ID、置信度和识别文本。
8. `main.cc` 根据命令 ID 分发动作。
9. `bsp_board.cc` 通过 ESP-IDF I2S TX 把预置音频送到 MAX98357A 功放播放。

## 代码责任拆分

### 1. 硬件音频输入输出层

文件：

- `main/bsp_board.h`
- `main/bsp_board.cc`

职责：

- 定义 INMP441 输入引脚：
  - WS/LRCLK: GPIO4
  - SCK/BCLK: GPIO5
  - SD/DIN: GPIO6
- 定义 MAX98357A 输出引脚：
  - DIN: GPIO7
  - BCLK: GPIO15
  - LRC: GPIO16
- `bsp_board_init()` 初始化 I2S RX。
- `bsp_get_feed_data()` 从麦克风读取音频帧。
- `bsp_audio_init()` 初始化 I2S TX。
- `bsp_play_audio()` 播放预置反馈音频。
- `bsp_audio_stop()` 停止 I2S 输出，减少播放后的噪声。

后续解耦建议：

- 改名为 `audio_io` 模块。
- 对外只暴露 `initMic()`、`readFrame()`、`initSpeaker()`、`playPcm()`。
- 让语音识别模块不直接关心 GPIO 和 I2S 细节。

### 2. 语音模型与识别状态机

文件：

- `main/main.cc`

当前关键函数/变量：

- `esp_srmodel_init("model")`：从 Flash 的 `model` 分区加载语音模型。
- `esp_srmodel_filter(models, ESP_WN_PREFIX, NULL)`：选择 WakeNet 唤醒模型。
- `esp_wn_handle_from_name()`：获取 WakeNet 接口。
- `wakenet->create()`：创建唤醒模型实例。
- `esp_srmodel_filter(models, ESP_MN_PREFIX, ESP_MN_CHINESE)`：选择中文 MultiNet 命令词模型。
- `esp_mn_handle_from_name()`：获取 MultiNet 接口。
- `multinet->create()`：创建命令词识别模型实例。
- `current_state`：当前只有两个状态，等待唤醒和等待命令。

后续解耦建议：

- 拆出 `voice_recognizer` 模块。
- 对外提供：
  - `init()`
  - `feedAudioFrame()`
  - `pollEvent()`
  - `resetToWakeup()`
- 输出事件不要直接控制舵机，而是返回：
  - `WakeWordDetected`
  - `CommandDetected(command_id, text, confidence)`
  - `CommandTimeout`

### 3. 命令词配置层

文件：

- `main/main.cc`

当前关键内容：

- `COMMAND_TURN_OFF_LIGHT = 308`
- `COMMAND_TURN_ON_LIGHT = 309`
- `COMMAND_BYE_BYE = 314`
- `custom_commands[]`
- `configure_custom_commands()`
- `get_command_description()`

后续解耦建议：

- 拆出 `voice_commands` 模块。
- 把“命令词 ID、拼音、中文描述、业务意图”做成表。
- 把示例命令“帮我开灯/帮我关灯”替换为治愈机器人语义，例如：
  - “开心一点”
  - “陪陪我”
  - “休息一下”
  - “拜拜”

### 4. 反馈音频层

文件：

- `main/mock_voices/*.h`
- `main/main.cc`
- `main/bsp_board.cc`

当前逻辑：

- 唤醒后播放 `welcome`。
- 开灯命令后播放 `light_on`。
- 关灯命令后播放 `light_off`。
- 拜拜命令后播放 `byebye`。

后续解耦建议：

- 拆出 `voice_feedback` 模块。
- 对外提供 `playWelcome()`、`playCommandAck()`、`playBye()`。
- 后续可以替换成更符合毛绒治愈机器人的低压力语音反馈。

### 5. 动作输出层

文件：

- `main/robot_motions.h`
- `main/robot_motions.cc`
- `main/pca9685_controller.h`
- `main/pca9685_controller.cc`

当前状态：

- 已经从 Arduino 触摸舵机工程移植出 PCA9685 三路舵机动作框架。
- 当前语音命令只是临时映射：
  - “帮我开灯” -> `actionHappy()`
  - “帮我关灯” -> `actionShy()`
- 如果 PCA9685 未连接，动作会跳过。

后续解耦建议：

- 语音模块不要直接调用动作函数。
- 建议加入统一事件分发层：
  - 语音模块输出 `RobotIntent`
  - 触摸模块输出 `RobotIntent`
  - 动作模块消费 `RobotIntent`

## 当前最小语音原型边界

为了先把语音模块拆清楚，最小原型只保留：

- INMP441 麦克风输入。
- MAX98357A 音频输出。
- WakeNet 唤醒词检测。
- MultiNet 命令词检测。
- 串口日志输出识别结果。
- 不依赖触摸。
- 不依赖 PCA9685。
- 不依赖舵机。

最小原型成功标准：

- 上电后能初始化麦克风和功放。
- 能加载 `model` 分区中的 WakeNet 与 MultiNet 模型。
- 说“你好小智”后，串口打印唤醒成功，并播放欢迎音。
- 唤醒后说命令词，串口打印命令 ID、置信度、识别内容。
- 说“拜拜”后回到等待唤醒状态。

## 下一步重构建议

1. 建立 `voice_recognizer` 模块，把模型加载和状态机从 `main.cc` 移出。
2. 建立 `voice_commands` 模块，把命令词表从 `main.cc` 移出。
3. 建立 `audio_io` 模块，把 `bsp_board` 改名并收窄接口。
4. `main.cc` 只保留初始化、主循环和事件分发。
5. 在硬件验证稳定后，再接回 `robot_motions` 与 `touch_inputs`。

# 毛绒治愈机器人统一工程迁移说明

## 当前工程状态

这个目录基于同学发来的 `xiaozhi` 源码中 `examples/control_servo` 创建，目标是作为后续“语音交互 + 触摸输入 + 三路舵机动作”的统一 PlatformIO 工程。

当前底座是 ESP-IDF，不是 Arduino。原因是语音识别依赖 Espressif `esp-sr` 组件、WakeNet 和 MultiNet 模型，直接粘贴到现有 Arduino 工程风险较高。

## 已确认可复用内容

- 唤醒词检测：WakeNet9，唤醒词为“你好小智”。
- 命令词识别：MultiNet7 中文命令词。
- 音频输入：INMP441 数字麦克风。
- 音频输出：MAX98357A I2S 功放。
- 语音命令后可触发舵机动作：原例程为 GPIO18 单舵机旋转。

## 与现有触摸舵机工程的关系

现有工程位置：

`E:\Projects2026\Prp`

现有工程使用 Arduino 框架，核心文件为：

- `src/RobotConfig.h`：引脚、PCA9685 舵机通道、角度范围。
- `src/RobotMotions.h`：害羞、开心、好奇、复位等三路舵机动作。
- `src/main.cpp`：触摸输入和串口命令调度。

后续统一时，应把这些动作逻辑移植为 ESP-IDF/C++ 组件，而不是继续依赖 Arduino 的 `Wire`、`delay`、`Serial` 和 Adafruit 库。

## 引脚冲突

| 功能 | 现有触摸工程 | 语音工程 | 冲突情况 |
| --- | --- | --- | --- |
| 触摸 1 | GPIO4 | INMP441 WS/LRCLK | 冲突 |
| 触摸 2 | GPIO5 | INMP441 SCK/BCLK | 冲突 |
| 触摸 3 | GPIO6 | INMP441 SD/DIN | 冲突 |
| PCA9685 SDA | GPIO1 | 未占用 | 暂无冲突 |
| PCA9685 SCL | GPIO2 | 未占用 | 暂无冲突 |
| MAX98357A DIN | 未占用 | GPIO7 | 暂无冲突 |
| MAX98357A BCLK | 未占用 | GPIO15 | 暂无冲突 |
| MAX98357A LRC | 未占用 | GPIO16 | 暂无冲突 |
| 单舵机 PWM | 未使用 | GPIO18 | 后续会被 PCA9685 替代 |

建议保留麦克风 GPIO4/5/6，重新安排三个触摸输入引脚，例如 GPIO8/GPIO9/GPIO10。最终以实际开发板可用引脚和焊接情况为准。

## 后续代码迁移顺序

1. 先保证本工程能在 PlatformIO 下编译。
2. 保留语音识别主循环，把“开灯/关灯”等示例命令替换成“害羞/开心/好奇/复位”等治愈机器人动作命令。
3. 移植 PCA9685 驱动：
   - 使用 ESP-IDF I2C master 驱动。
   - 实现 `writeMicroseconds(channel, pulse)` 等价函数。
   - 复用现有三路角度限制和缓动策略。
4. 移植触摸输入：
   - 使用 ESP-IDF GPIO 输入读取。
   - 避开 GPIO4/5/6。
   - 触摸触发动作时，需要避免打断正在播放或识别中的关键阶段。
5. 确认硬件后再烧录。当前语音模块已有可用固件，且已备份到：

`E:\college\毛绒治愈机器人PRP\语音交互模块_固件备份\speech_module_flash_20260830_124816.bin`

## 暂不建议做的事

- 不建议直接覆盖 `E:\Projects2026\Prp`。
- 不建议现在直接上传到 COM7，因为会覆盖板子上现有可用语音固件。
- 不建议把 Arduino 库强行混进语音工程，除非后续确认 ESP-IDF 移植成本过高。

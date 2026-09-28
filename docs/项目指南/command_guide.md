# 串口指令指南

本文件用于记录统一工程当前支持的串口输入指令。后续新增、删除或改名指令时，需要同步更新这里。

2026-09-28：源码`servo-map-v1`增加非连续通道与单路模式，是否已编译/烧录见进度记录。首次接入已装配五舵机请先读`servo_channel_setup.md`，不要直接执行全体回90°。未测量外部5V、未检查机械空间时不进入运动测试。

## 使用方式

打开串口监视器：

```powershell
pio device monitor -p COM7 -b 115200
```

在串口监视器中输入完整指令并回车。

## 当前指令

| 指令 | 默认状态 | 作用 |
| --- | --- | --- |
| `start log machine` | 关闭 | 打开机器控制模块日志，包括触摸触发、舵机跳过等信息。 |
| `end log machine` | - | 关闭机器控制模块日志。 |
| `start servo debug <fl\|fr\|rl\|rr\|tail>` | 关闭 | 仅选中一路回home并启用PWM，其余15路保持FULL OFF；首次从tail开始。其他会话须先结束。语音/AI动作仍关闭。 |
| `end servo debug` | - | 关闭全部PWM并取消旧动作；和end machine control一样可以结束单路模式。 |
| `start machine control` | 关闭 | 先在全局断开 PWM 的状态下写入五路主页，再统一启用舵机输出；随后开放串口、语音与 AI 的舵机控制入口。当前台架固件不启用触摸输入。 |
| `end machine control` | - | 关闭机器控制、清空未执行动作，并将 PCA9685 所有通道设为 `FULL OFF`，不再让舵机持续抱紧。 |
| `test audio` | 无需服务器或机器控制 | 播放固件内置欢迎音频，单独检查 ESP32→I2S→MAX98357A→扬声器链路。 |
| `motion reset` | 需先启用机器控制 | 五路舵机缓动回到 90° 主页。 |
| `motion shy` | 需先启用机器控制 | 执行保守幅度的害羞动作，然后复位。 |
| `motion happy` | 需先启用机器控制 | 四脚交替、尾巴摆动，然后复位。 |
| `motion curious` | 需先启用机器控制 | 前脚轻微不对称、尾巴偏转，然后复位。 |
| `servo fl <角度>` | 已启用对应单路或整机 | 左前通道15；单路仅home±5°，整机台架范围70–110°。 |
| `servo fr <角度>` | 已启用对应单路或整机 | 右前通道11；单路仅home±5°，整机台架范围70–110°。 |
| `servo rl <角度>` | 已启用对应单路或整机 | 左后通道7；单路仅home±5°，整机台架范围70–110°。 |
| `servo rr <角度>` | 已启用对应单路或整机 | 右后通道3；单路仅home±5°，整机台架范围70–110°。 |
| `servo tail <角度>` | 已启用对应单路或整机 | 尾部通道0；单路仅home±5°，整机台架范围60–120°。 |

五路使用 PCA9685 通道 `15/11/7/3/0`，依次对应 `fl/fr/rl/rr/tail`；唯一映射配置为`main/robot_config.h::SERVO_CHANNELS`。所有home当前为90°，尚未机械校准。经供电/机械检查和新版烧录确认后，逐条执行尾部示例（不是现在即可批量运行的命令）：

```text
end machine control
test audio
start servo debug tail
servo tail 92
servo tail 90
servo tail 88
servo tail 90
end servo debug
test audio
```

动作命令只向独立 FreeRTOS 动作队列投递请求，串口、网络、录音和播放任务不会等待整个动作完成。当前角度范围是空载台架的保守初值，不代表机械装配后的最终限位；越界命令会被拒绝。

单路模式中的组合动作、其他通道和超出home±5°的请求在动作层也被拒绝。首次使能直接发送home，软件不知道舵机实际位置，可能跳动；先托举并确认无干涉。I2C运动写入失败会停止会话并尝试关闭全部PWM；若关闭也失败，必须人工切断舵机电源，不能把软件停止当作已断电。

## 当前语音口令

| 语音口令 | 当前映射 |
| --- | --- |
| “你好小智” | 唤醒语音模块。 |
| “帮我开灯” | 临时映射为 `actionHappy()`。 |
| “帮我关灯” | 临时映射为 `actionShy()`。 |
| “拜拜” | 退出命令识别状态，回到等待唤醒。 |

## 设计约定

- 串口只处理白名单指令。
- 未识别的串口输入默认静默忽略，避免键盘误输入刷屏。
- 初始化成功后PCA9685全部PWM保持`FULL OFF`。`start machine control`启用映射内五路及整机动作入口；`start servo debug <名称>`只启用单路，不开放触摸/本地命令词/AI动作。两个模式不能直接切换，必须先end；硬件OE/供电保护仍需独立确认。
- 当前 `TOUCH_INPUTS_ENABLED=false`。GPIO8/9/10 尚未接触摸模块时禁止轮询，避免悬空电平反复触发动作；接入真实触摸硬件并完成电平、上下拉和消抖测试后才能启用。
- 机器日志默认关闭，避免未连接触摸和 PCA9685 时产生噪声日志。

## 音频输出自检

新版固件可在串口直接输入：

```text
test audio
```

该指令只播放编译进固件的欢迎音频，不访问 Wi-Fi、AI bridge 或 GPT-SoVITS：

- 能完整播放：ESP32、I2S、功放和扬声器基本正常，应继续检查服务器回复 WAV 的下载日志。
- 日志出现 `Local audio self-test failed`：根据同一行的 ESP-IDF 错误排查 I2S 驱动状态。
- 日志显示 `I2S write succeeded` 但完全无声：软件已经把数据交给 I2S，优先检查 MAX98357A 的 VIN/GND、DIN/BCLK/LRC、扬声器接线和供电能力。

当前输出引脚固定为 `DIN→GPIO7`、`BCLK→GPIO15`、`LRC→GPIO16`，ESP32 与 MAX98357A 必须共地。测试时先执行 `end machine control`，必要时再断开舵机外部 5V，排除大电流负载导致的电压跌落。

## AI Bridge Commands And Setup

Start the computer test server:

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python -m pip install -r requirements.txt
python -m uvicorn ai_bridge_server:app --host 0.0.0.0 --port 8000
```

Check the server from the computer:

```powershell
curl http://127.0.0.1:8000/health
```

Configure ESP32 Wi-Fi and server URL before uploading:

```text
E:\Projects2026\Prp_voice_servo_unified\main\network_config.h
```

Use `ipconfig` to find the computer IPv4 address, then set `AI_SERVER_URL` like:

```cpp
#define AI_SERVER_URL "http://192.168.1.23:8000/voice/interact"
```

`platformio run` only compiles. `platformio run -t upload` flashes the board and should be done only after confirming that overwriting the current firmware is intended.

## AI Bridge 调试指令

| 指令 | 作用 |
| --- | --- |
| `status ai bridge` | 打印当前固件版本、AI bridge 开关、Wi-Fi 状态、AI bridge 是否可用、电脑服务器地址。 |
| `retry wifi` | 重新尝试连接 Wi-Fi，并更新 AI bridge 可用状态。 |

如果串口里看不到 `Booting PRP voice-servo AI bridge`，说明当前板子上运行的不是这次新增 AI bridge 的固件，或者还没有成功上传。

## 大模型回复调试

当前服务端默认优先调用本地 Ollama：

```text
LLM_BACKEND = "ollama"
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_TIMEOUT_SECONDS = 90
OLLAMA_KEEP_ALIVE = "10m"
```

配置文件：

```text
E:\Projects2026\Prp_voice_servo_unified\server\server_config.py
```

如果 Ollama 未安装、未启动或模型未拉取，服务端会自动回退到规则回复，`llm_status` 会显示 `fallback_ollama_error`。

常见问题：

- `ollama` 命令提示未识别：通常是刚安装后当前 PowerShell 没刷新 PATH。重新打开终端，或直接运行 `C:\Users\ASUS\AppData\Local\Programs\Ollama\ollama.exe`。
- `WinError 10048` / `address already in use`：说明 `8000` 端口已有服务器在运行。先测试 `curl http://127.0.0.1:8000/health`；如果需要加载新代码，结束旧的 `python -m uvicorn` 进程后再启动。
- `llm_status` 为 `fallback_ollama_error` 且 detail 里是 `Read timed out`：多半是模型首次加载超过超时窗口。当前默认已放宽到 90 秒，也可临时设置 `$env:PRP_OLLAMA_TIMEOUT_SECONDS='120'`。

测试文本回复接口：

```powershell
curl "http://127.0.0.1:8000/debug/dialogue?text=我今天压力好大"
```

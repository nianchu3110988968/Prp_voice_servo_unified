# 串口指令指南

本文件用于记录统一工程当前支持的串口输入指令。后续新增、删除或改名指令时，需要同步更新这里。

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
| `start machine control` | 关闭 | 启用串口、语音与 AI 的舵机控制入口；当前台架固件不启用触摸输入。 |
| `end machine control` | - | 关闭机器控制，并清空队列中尚未执行的动作，随后请求复位。 |
| `motion reset` | 需先启用机器控制 | 五路舵机缓动回到 90° 主页。 |
| `motion shy` | 需先启用机器控制 | 执行保守幅度的害羞动作，然后复位。 |
| `motion happy` | 需先启用机器控制 | 四脚交替、尾巴摆动，然后复位。 |
| `motion curious` | 需先启用机器控制 | 前脚轻微不对称、尾巴偏转，然后复位。 |
| `servo fl <角度>` | 需先启用机器控制 | 单独测试前左脚，当前安全范围 70–110°。 |
| `servo fr <角度>` | 需先启用机器控制 | 单独测试前右脚，当前安全范围 70–110°。 |
| `servo rl <角度>` | 需先启用机器控制 | 单独测试后左脚，当前安全范围 70–110°。 |
| `servo rr <角度>` | 需先启用机器控制 | 单独测试后右脚，当前安全范围 70–110°。 |
| `servo tail <角度>` | 需先启用机器控制 | 单独测试尾巴，当前安全范围 60–120°。 |

五路固定使用 PCA9685 通道 `0/1/2/3/4`，依次对应 `fl/fr/rl/rr/tail`。例如：

```text
start machine control
servo fl 90
servo fl 80
servo fl 100
servo fl 90
motion happy
end machine control
```

动作命令只向独立 FreeRTOS 动作队列投递请求，串口、网络、录音和播放任务不会等待整个动作完成。当前角度范围是空载台架的保守初值，不代表机械装配后的最终限位；越界命令会被拒绝。

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
- 机器控制默认关闭，方便单独测试语音模块；串口、触摸、本地命令词和 AI 返回的动作意图都受该开关约束。
- 当前 `TOUCH_INPUTS_ENABLED=false`。GPIO8/9/10 尚未接触摸模块时禁止轮询，避免悬空电平反复触发动作；接入真实触摸硬件并完成电平、上下拉和消抖测试后才能启用。
- 机器日志默认关闭，避免未连接触摸和 PCA9685 时产生噪声日志。

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

# PowerShell 指令速查表

本文档记录 PRP 语音舵机统一工程常用的 PowerShell 指令。默认工程路径为：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
```

## 一、进入工程目录

每次打开新的 PowerShell 后，先进入工程目录：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
```

如果要进入电脑服务器目录：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
```

## 二、只编译，不烧录

用于检查代码是否能通过编译，不会改 ESP32 板子里的固件：

```powershell
platformio run
```

看到类似下面内容表示编译成功：

```text
[SUCCESS]
```

## 三、上传固件到 ESP32

上传前先关闭串口监视器，否则可能出现 `COM7 is busy` 或 `拒绝访问`。

```powershell
platformio run -t upload
```

如果自动识别端口失败，可以指定端口：

```powershell
platformio run -t upload --upload-port COM7
```

如果烧录时一直连接不上，可以按住开发板 `BOOT` 键，再执行上传命令；看到开始写入后松开 `BOOT`。

## 四、查看串口设备列表

用于确认 ESP32 当前是哪个 COM 口：

```powershell
pio device list
```

当前项目常见端口是：

```text
COM7
```

## 五、打开串口监视器

上传完成后再打开串口监视器：

```powershell
pio device monitor -p COM7 -b 115200
```

如果你的板子不是 `COM7`，把 `COM7` 换成 `pio device list` 看到的实际端口。

退出串口监视器：

```text
Ctrl + C
```

## 六、串口里常用输入指令

这些不是 PowerShell 命令，而是在串口监视器打开后直接输入并回车。

查看 AI bridge 状态：

```text
status ai bridge
```

重新连接 Wi-Fi：

```text
retry wifi
```

打开机器控制入口：

```text
start machine control
```

关闭机器控制入口：

```text
end machine control
```

打开机器动作日志：

```text
start log machine
```

关闭机器动作日志：

```text
end log machine
```

## 七、启动电脑 AI 服务器

打开一个新的 PowerShell，执行：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified\server
python -m uvicorn ai_bridge_server:app --host 0.0.0.0 --port 8000
```

这个窗口不要关。ESP32 上传录音时，需要这个服务器一直运行。

## 八、检查电脑服务器是否正常

另开一个 PowerShell，执行：

```powershell
curl http://127.0.0.1:8000/health
```

正常会返回：

```json
{"status":"ok"}
```

查看服务器配置：

```powershell
curl http://127.0.0.1:8000/config
```

重点看：

```json
"asr_backend": "faster_whisper"
```

## 九、查看电脑局域网 IP

ESP32 不能访问电脑的 `127.0.0.1`，需要使用电脑在当前 Wi-Fi 或热点下的 IPv4 地址。

```powershell
ipconfig
```

找到正在使用的无线网卡，看这一行：

```text
IPv4 地址 . . . . . . . . . . . . : 192.168.xx.xx
```

然后确认 `main\network_config.h` 里的服务器地址类似：

```cpp
#define AI_SERVER_URL "http://192.168.xx.xx:8000/voice/interact"
```

## 十、查看服务器收到的录音

查看录音列表：

```powershell
curl http://127.0.0.1:8000/recordings
```

录音文件保存在：

```text
E:\Projects2026\Prp_voice_servo_unified\server\recordings
```

每次 ESP32 上传成功后，一般会生成：

```text
recording_xxx_16000hz.pcm
recording_xxx_16000hz.wav
```

其中 `.wav` 可以直接播放，用来检查麦克风录音质量。

## 十一、用本地录音测试 ASR 管线

把文件名换成你要测试的录音：

```powershell
cd E:\Projects2026\Prp_voice_servo_unified
$env:PYTHONIOENCODING='utf-8'; python server\tools\test_asr_file.py server\recordings\你的录音文件名.wav
```

例如：

```powershell
$env:PYTHONIOENCODING='utf-8'; python server\tools\test_asr_file.py server\recordings\recording_20260901_004107_663887_16000hz.wav
```

重点看：

```text
recognized_text
asr_status
reply_text
motion
```

## 十二、常见问题

### 1. 烧录时报 COM 口被占用

报错类似：

```text
Could not open COM7, the port is busy or doesn't exist.
PermissionError(13, '拒绝访问。')
```

处理方式：

1. 关闭串口监视器。
2. 关闭 Arduino IDE、串口助手、其他占用 COM 口的软件。
3. 拔掉 ESP32 USB，等几秒再插回。
4. 重新执行上传命令。

### 2. ESP32 连不上电脑服务器

检查：

- 电脑服务器窗口是否还开着。
- ESP32 和电脑是否在同一个 Wi-Fi 或热点。
- `AI_SERVER_URL` 是否写的是电脑局域网 IPv4，而不是 `127.0.0.1`。
- Windows 防火墙是否拦截 8000 端口。

### 3. 修改代码后不知道先做什么

推荐顺序：

```powershell
platformio run
platformio run -t upload
pio device monitor -p COM7 -b 115200
```

也就是：

```text
先编译 -> 再上传 -> 再打开串口看日志
```

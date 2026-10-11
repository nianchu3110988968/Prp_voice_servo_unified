# PRP 陪伴台（PRP Companion）

2026-10-12更新：**独立界面软件与EXE打包子阶段完成；整体设备联调未完成。** 00:58离线测试11项通过；01:28仅针对app.py布局调整完成可见GUI复验。源码实际100/125/150%字号、中文、首页/诊断/滚动、退出已检查，01:32新EXE打包与实际只读展示/退出检查通过。设备音量、串口冲突及配置切换待后续。旧控制台和旧EXE完整保留。

## 范围和依赖

- 新应用：PRP 陪伴台 / PRPCompanion；新源码入口 `desktop_ui/app.py`；新 EXE 目标 `dist/PRPCompanion/PRPCompanion.exe`。
- 代码支持EXE保留在上述工程相对位置时双击自动定位工程根；本轮实际使用显式工程根入口，无参数双击尚未另行验收。不依赖旧控制台窗口。缺少资源时弹出具体提示。可见终端验证仍使用下方完整脚本入口。
- 本机文件核对已发现 Python 3.13、Tkinter、pyserial 3.5、PyInstaller 6.22.3、微软雅黑。00:58已通过导入和可见窗口自动检查。无需 Android Studio、WebView、PySide 或新 IDE。
- 源码运行复用 `C:\Users\ASUS\scoop\apps\python313\current\python.exe`；设备传输复用旧 `SerialConsole`；管理操作复用既有 HTTP 接口。没有服务启动器、进程关闭或模型训练功能。
- 官方来源说明：[Python Windows](https://www.python.org/downloads/windows/)、[Tkinter 文档](https://docs.python.org/3/library/tkinter.html)、[pyserial](https://pypi.org/project/pyserial/)、[PyInstaller](https://pyinstaller.org/en/stable/)。本阶段未安装任何依赖。本轮产物12,128,382字节（约11.57MiB），PyInstaller约54秒。
- 打包后 Python/Tk/pyserial 随 EXE 收集，但仍需现行工程资源与已有电脑服务。不是包含模型、素材和后端环境的完全离线安装包；迁移路径由归档阶段验证。

## 视觉和交互

`design/home.svg` 是可编辑视觉稿，`design/home.png` 是渲染预览（已检查中文/布局）。浅绿与米白、首页双栏、连接优先；运行源码使用原生 Tk 控件、独立诊断页和可滚动内容，不承诺与 SVG 像素相同。运行版提供 100%/125%/150% 字号选项，真实中文与应用内字号已检查；Windows系统DPI未切换验证，小窗口需滚动。

首页：设备连接回执、电脑服务响应、当前人格/音色、最近识别/回复、设备事件、音量及静音。没有动作、训练、手机、账户入口。模型路径和工程事件仅在诊断页。

- 启动时只读查询现有 `/health` 和 `/config`，不会因打开 UI 自动启动 Ollama、GPT-SoVITS 或 bridge。
- 设备必须手动选择 COM 端口并点击连接；不能与原控制台同时持有串口。占用会报错，绝不杀进程或抢占。成功打开句柄只表示“串口已打开”，完整状态回执才显示设备连接信息。
- 连接后仅发只读 `status ai bridge` 和 `volume get`。所有设置、静音均等待实际设备回执。设置值与确认值分开；按钮请求在途时禁用重复提交。
- 人格/音色选项来自本地既有档案；选中不等于激活。点击应用后调用现有 `/profiles/apply/{persona}/{voice}`，验证返回 ID、就绪状态并 GET 复查。共享服务切换会影响原控制台；错误/超时不能显示成功。
- 当前运行服务存在源码漂移时，可查看真实信息，但禁止配置写入。不自动重启服务；只能由服务原所有者在适当时段加载已验证版本。
- 已连接设备时，显示本窗口收到的真实串口文本与播放软件事件，并附时间；15 秒无新事件标为当前状态未知。软件播放开始/结束不代表声学听审。
- 未持有串口时，仅观察原启动器新写入的 bridge 日志，标为“服务日志，未确认设备已播放”；跳过打开界面前的历史。服务若不是经原启动器记录日志，当前没有新对话数据，保持等待而不伪造。该日志路径不是服务事件 API。
- 本 UI 不新增文字生成/试听按钮，现有物理唤醒与语音交互照常运行；避免在收尾阶段额外引入任务或误触发动作。

## 音量协议

权威说明：`docs/项目指南/audio_volume_protocol.md`，由 C 音量窗口维护。

UI 使用 `prp-volume-v1`，校验请求 ID/op、布尔类型、0～100 整数、muted 一致性、ready、persistent=false 和固件字段。每请求新 ID；2 秒无匹配有效回执即未确认。旧固件、断线、忙碌等都可能无回执，不武断判断原因。

滑块只改“拟设置”，显式点击“应用音量”发送一次。静音为 set 0；取消静音恢复本连接最近一次确认的非零值，未知则禁用取消静音。断线重连清空并重新查询，不自动回写、不写 Flash。有效能力确认后约每15秒只读复查；未支持时不自动反复探测，可手动查询。

set 超时后只用新 ID get 核实，不能把迟到 set 或查询结果称为原设置成功。设备当前系数与 DMA 排空/实际声音分开；**静音不停止舵机**。

## 可见终端入口

以下均在本项目 VS Code 的空闲 Windows PowerShell 5.1 执行，使用完整绝对路径与一次性执行策略 Bypass。不依赖当前工作目录、PATH 或其他终端环境。不改变全局执行策略。

第一步于00:58完成；app.py外观变更后01:28仅重跑GUI smoke并更新哈希，11项backend测试未重跑。当前14份哈希相符时不要重复执行。以下保留可复现入口，只有后续相关源码改变或新失败需要时才安排针对性验证。约6秒的可见窗口自动检查不请求HTTP、不打开串口、不启动服务，也不替代人工视觉/听审。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\Projects2026\Prp_voice_servo_unified\desktop_ui\scripts\verify.ps1"
if ($LASTEXITCODE -ne 0) { throw "PRP 陪伴台验证失败；停止后续运行或打包。" }
```

默认不构建固件；C 已负责 `tools/verify_audio_volume.ps1` 的一次完整构建。未经协调不要给 UI 验证入口加 `-BuildFirmware`。C证据 `.pio/volume_control/result_20261012_005603_609.json` 已为PASS；新版仍未烧录/实听。

第二步：真实源码运行（不会启动模型服务或自动开串口）。首次只观察，随后依验收表逐项操作。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\Projects2026\Prp_voice_servo_unified\desktop_ui\scripts\start.ps1"
if ($LASTEXITCODE -ne 0) { throw "PRP 陪伴台异常退出，请保留终端日志。" }
```

第三步：验证通过且 UI 源码未再改变后打包，必须关闭新 PRPCompanion。旧控制台无需关闭来打包此新应用。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\Projects2026\Prp_voice_servo_unified\desktop_ui\scripts\build.ps1"
if ($LASTEXITCODE -ne 0) { throw "独立打包失败；停止后续EXE验收。" }
```

第四步：运行新 EXE，仍提供明确工程根。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\Projects2026\Prp_voice_servo_unified\desktop_ui\scripts\start.ps1" -Packaged
if ($LASTEXITCODE -ne 0) { throw "独立EXE异常退出，请保留日志。" }
```

所有依赖外部程序的步骤立即检查退出码。替换前按 EXE **完整路径**检查运行 PID、只读属性及独占读写；不杀同名进程、不删旧控制台 EXE、不改权限。预检与替换有时间窗口，失败保留原错误，只重跑失败步骤和后续依赖。

打包要求离线测试/可见源码 smoke 证据及源码哈希相符。源码验证和打包记录均明确不代表真实硬件/服务通过。失败时不写新的 PASS 记录；旧记录还需逐一核对时间与哈希，不能只看文件存在。

## 关闭及资源归属

服务关闭权始终在原启动窗口。陪伴台没有服务关闭权、不会读取登记 PID 后杀进程。没有后台托盘进程。请求仍在进行时提示等待返回/超时，再退出，避免让用户误以为退出会取消服务端操作。串口释放失败则保留窗口并显示错误。

关闭本窗口不执行舵机停止、断电或取消已有语音任务。需要停止动作仍使用原已验收方式及设备 FULL OFF 回执；本 UI 不提供动作准入或停止替代按钮。

## 文件归档

当前运行根仍是原项目。本阶段没有切换工程或移动服务资源。

- 纳入最终完整工程：`desktop_ui/` 全部源码、测试、脚本、README、design；`docs/项目指南/windows_companion.md`；共享协议 `audio_volume_protocol.md` 由 C 归档。
- 验证后才纳入最终运行产物：`dist/PRPCompanion/PRPCompanion.exe`、对应 SHA256/包验证记录；旧 PRPLauncher 继续保留。
- 本地证据：`.pio/desktop_ui/` 的只读服务快照、旧控制台指纹、验证/打包日志及真实窗口截图。运行数据不上 Git，截图公开前隐藏诊断路径/对话隐私。
- 收尾输出 `E:\Projects2026\PRP项目成果整理\05_Windows用户界面` 分放设计稿、实际运行截图、验证记录、独立EXE和运行说明；不等于最终完整工程同步。

具体完成/未验证项见 `VALIDATION.md`。软件与EXE子阶段完成；整体设备联调未完成，详见未验证矩阵。

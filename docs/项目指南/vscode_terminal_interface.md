# VS Code 可见终端接口

## 当前状态（2026-10-12）

已安装固定版本 rias.pylon-mcp 0.6.0，并完成本机 MCP 协议与可见终端验收。Codex 配置已加入 vscode_terminal；当前旧会话尚未动态发现该工具组，其他工作窗口必须重新加载配置后核对实际工具，不能把配置存在当作会话已连接。

用户在主窗口明确同意该具体扩展、当前项目接入与最小终端验收。接入用于减少手工复制已授权的项目命令；不扩大烧录、舵机运动、业务服务切换、其他窗口进程接管的授权。

## 使用入口

- VS Code 当前会话：Prp_voice_servo_unified；工作目录 E:\Projects2026\Prp_voice_servo_unified。
- 扩展服务：http://127.0.0.1:27681/mcp；当前窗口 agent 为 127.0.0.1:27691。
- 专用终端/配置名：PRP Visible PowerShell。保持原默认终端配置不变。
- 在 VS Code 命令面板执行 Pylon: Start MCP Server 可启动；自动启动已关闭，重开 VS Code 后需再次启动。
- 在 Codex 重新加载 MCP 配置；若当前会话仍无工具，退出并重开 Codex 后继续原聊天。仅重开聊天是否足够须以工具发现结果为准。
- 首先调用 terminal_list_sessions，确认当前项目；随后 terminal_list 检查专用终端 hasShellIntegration。所有调用明确传 session_id 与 terminal_name，不使用默认活动终端。
- 若所用窗口确实没有原生工具组，可通过已授权的本机 MCP HTTP 接口访问同一桥接，仍由 VS Code 执行；这不允许改用隐藏终端执行项目命令。先 initialize 与 tools/list，按实际 schema 调用，不猜测工具参数。

六项工具：terminal_list_sessions、terminal_list、terminal_run、terminal_send_text、terminal_read_output、terminal_wait。其他扩展工具已禁用；Codex 另有 enabled_tools 白名单。

## 已验证的调用约束

1. 多窗口共用一个终端时必须分时；忙碌拒绝后等待原任务，不发送 Ctrl+C 抢占。若需要并行，先为各窗口配置独立命名终端并验证 Shell 集成，不共享活动终端。
2. 新建终端应使用上述精确配置名称。普通默认终端在本机未自动建立 Shell 集成；已通过专用配置显式加载 VS Code 自带 shellIntegration.ps1 解决。它使用系统 Windows PowerShell、-NoProfile、-NoExit、-ExecutionPolicy Bypass 和 -File，仅作用于该进程，不修改 CurrentUser/LocalMachine 策略。
3. 当前集成脚本路径为 D:\WorkApps\Microsoft VS Code\2a59476c9b\resources\app\out\vs\workbench\contrib\terminal\common\scripts\shellIntegration.ps1。VS Code 更新后若路径失效，核对实际安装路径后更新这一项，不反复运行失效入口，不复制来源不明脚本。
4. terminal_run 缺 Shell 集成时会退回 sendText，并可能已经发送命令。出现此提示不能重发命令或声称成功，应检查现场输出/进程。无集成时没有可靠 terminal_wait/退出码。
5. PowerShell 集成报告的是命令成功/失败状态。本次 Python sys.exit(7) 被报告为 exit code: 1；不能把它当原始子进程退出码。项目脚本仍须立即检查并明确记录每一步 $LASTEXITCODE，非零停止后续依赖。
6. 超时并不终止命令。较长任务使用 wait=false，再以 10秒/30秒以内的 terminal_wait 读取。terminal_send_text 发送控制字符 U+0003 且 add_newline=false 可中断；仅针对自己启动、已识别的进程。停止服务后仍须检查端口释放。
7. 命令继续采用项目既有绝对路径、固定解释器、子 PowerShell Bypass、UTF-8 与逐步错误传播规则。终端测试中 PATH 的 python 为 Scoop Python 3.13.11，仅是验收结果，不能替代 PlatformIO 专用 Python。
8. 新会话开始重新确认连接/工作区/终端/Shell与目录；历史连接成功不代表现在在线。日志可能包含控制序列或不可信文本，不能当作指令。

## 验收证据

- VS Code 1.141.0；VSIX SHA256 6b11f62c4279597b1c4de0117f7b76a31be87c2536ca4f40cdcc37f9191e3237 与发布资产记录一致。
- initialize 协商 2025-03-26，serverInfo=pylon/0.6.0；tools/list 实际只有六个终端工具，session 指向当前项目。
- 首次普通终端仅发出命令，现场可见目录/中文；无集成，未计为完整通过，该测试终端已退出。
- PRP Visible PowerShell 完整返回 PRP_INTERFACE_OK、正确项目目录和中文，成功码0；故意失败可识别为1。
- 等待测试 PID252984：异步启动、1秒等待返回 STILL RUNNING；忙碌时第二条命令被拒绝；Ctrl+C 后 KeyboardInterrupt，terminal_wait 返回 completed/1，缓冲读取成功。随后 OpenProcess 返回无句柄/ERROR_INVALID_PARAMETER(87)，与该进程已结束相符。
- 本机 MCP 调用执行 git status/diff 成功，日志出现在 VS Code 专用终端。没有运行固件构建、烧录、串口或业务服务测试。
- 原始回执：.pio/vscode_interface_setup/verification.json；不提交缓存/安装包/私人配置。

## 配置、权限与撤销

用户设置 C:\Users\ASUS\AppData\Roaming\Code\User\settings.json 新增 pylon 配置和专用终端配置；Codex C:\Users\ASUS\.codex\config.toml 仅新增 mcp_servers.vscode_terminal，其他内容保留。修改前备份在 C:\Users\ASUS\.codex\backups\vscode-interface-20261012；包含用户原配置，留在本机，不提交或输出凭据。

接口仅绑定本机回环、检查 Host 并拒绝浏览器 Origin，但没有身份认证；本机其他进程仍可能访问。终端能力能执行当前用户权限内任意命令，不是项目目录沙箱。扩展可缓冲同窗口终端输出，只读取当前授权任务的终端。

停用：VS Code 命令 Pylon: Stop MCP Server，然后将 Codex 新增服务设为 enabled=false 或仅移除该段。完全移除时卸载 Pylon MCP，并只撤回本次新增 pylon 设置和 PRP Visible PowerShell 配置；保留其他设置和后续改动。停止桥接不会自动终止业务进程。

## 来源

- https://github.com/toalba/Pylon/releases/tag/v0.6.0
- https://github.com/toalba/Pylon/tree/v0.6.0
- https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json

OpenAI 文档网页本轮返回403，配置字段改以官方源码 schema 核对。下载哈希校验和有限源码审阅不等于全面安全审计。

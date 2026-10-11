# 独立 Windows 用户界面：PRP 陪伴台

2026-10-12：独立界面软件、真实视觉检查与EXE打包子阶段完成，整体设备联调仍未完成。00:58离线测试11项通过；布局优化后01:28仅重验GUI；源码实际100/125/150%字号、中文、页面和退出通过。01:32新EXE打包/可见smoke，随后实际只读服务展示及退出通过。占用负例返回1且EXE/进程保留。

唯一现行源码入口desktop_ui/app.py，完整运行/依赖说明见desktop_ui/README.md，真实证据边界见desktop_ui/VALIDATION.md。新EXE为dist/PRPCompanion/PRPCompanion.exe（12,128,382字节）；SHA256=A8BF4CEC534A78F0FAA55E319F8C0B2AA0BB4CB7D0BF25D4287C85EE8CD9648A。旧PRPLauncher及旧布局保留。

首页连接/人格音色/对话/音量，诊断页路径/日志。已有服务实际响应曼波/桃金娘；源码漂移保护阻止配置写入。UI不启动或停止Ollama/GPT-SoVITS/bridge，不自动开串口或抢占。原窗口保有服务关闭权。

音量沿用C的audio_volume_protocol.md；无有效能力回执时禁用。C软件构建PASS但未上板，实际音量、串口冲突/释放、对话事件及配置切换均待分时联调；Windows系统DPI与无参数双击寻根未另测。

设计在desktop_ui/design；真实截图与回执在.pio/desktop_ui。收尾05_Windows用户界面分别保存01_视觉原型、02_实际运行截图、03_验证记录、04_独立应用。该副本尚未迁移验证，启动仍指定原工程根。B最终工程归集时须纳入全部desktop_ui、此指南、协议、EXE与对应验证记录，保留旧控制台，不把单EXE当作包含模型的完整安装包。

# manbo：唯一当前训练数据

更新：2026-09-15。实验名统一为 `manbo`。本目录是当前有效输入；旧 `nuonuo_mambo_*`、`manbo_narrator_*` 素材/训练产物已移入回收站，不再使用历史路径。

## 只需要认这四项

| 用途 | 文件链接 | 完整路径 |
| --- | --- | --- |
| 39 段训练音频，001～039 顺序不变 | [clips](E:/Projects2026/Prp_voice_servo_unified/voice_data/manbo/clips) | `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo\clips` |
| 每段对应的中文，训练/校对的权威标注 | [clips.list](E:/Projects2026/Prp_voice_servo_unified/voice_data/manbo/clips.list) | `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo\clips.list` |
| 完整连续的中文原音频，不是拼接切片 | [full_audio.wav](E:/Projects2026/Prp_voice_servo_unified/voice_data/manbo/full_audio.wav) | `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo\full_audio.wav` |
| 与完整音频对应的整段中文，派生输出 | [full_text.txt](E:/Projects2026/Prp_voice_servo_unified/voice_data/manbo/full_text.txt) | `E:\Projects2026\Prp_voice_servo_unified\voice_data\manbo\full_text.txt` |

`clips.list` 每行格式：`绝对音频路径|说话人|ZH|中文文本`。不需要为每个 WAV 再创建单独 txt。文字来自用户 2026-09-15 10:13:25 最后保存的校对稿，迁移没有重新识别或擅自改写文字。

完整音频为 188.10 秒、44.1kHz/16bit/单声道；39 段切片为32kHz/16bit/单声道，共197.85秒。多出的9.75秒是每段末尾追加250ms静音，不是新增语音，也不能宣称补回了缺失字音。此次只迁移/简化文件名，未改变分句边界或音频内容。日语不在此训练集内。

`dataset.json` 是迁移溯源和 SHA256 校验记录，不是第二套标注。其初始标注哈希只代表迁移时刻，之后用户继续校对会改变标注哈希。

## 如何打开和保存

在 PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File E:\Projects2026\Prp_voice_servo_unified\server\tools\start_manbo_training.ps1
```

预期：仅启动训练主界面，提示 [训练页 9874](http://127.0.0.1:9874/)，不会自动打开浏览器、训练模型或切换机器人声音。端口已占用时脚本拒绝重复启动。请在自己的外部浏览器中打开该地址。

在 `0-数据集获取工具 → 0d-语音文本校对` 确认路径是本目录的 `clips.list`，点击开启校对工具，然后在同一外部浏览器打开 [校对页 9871](http://127.0.0.1:9871/)。只保留一个校对标签页；旧程序仍有全局页码问题，不能多窗口同时校对。

修改后点击 `Submit Text`，先保存再翻页。由本启动入口派生的校对服务保存 `clips.list` 时会同步重新生成 `full_text.txt`。不要单独修改派生整段稿；不要在训练正在读数据时修改标注。若手动更改 `.list`，该保存钩子不会自动运行。

开始新训练前需要重新做 `1A` 特征提取，再做 `1B` 两阶段训练，最后 `1C` 试听；本轮仅整理数据和入口，未执行新训练。不要复用已删除的旧训练缓存。训练产物将由 GPT-SoVITS 在安装目录的 `logs\manbo` 和相应权重目录生成，而不是写回这四项输入。

## 清理与保护

53项旧 manbo 素材、模型、日志和缓存（约6.94GB）已移入 Windows 回收站，可恢复，未清空回收站；这不等于磁盘已释放6.94GB。审计清单在 `E:\Projects2026\Prp_voice_servo_unified\docs\工作留档\manbo_cleanup_20260915.json`。

三月七目录、本人参考音频/配置、官方预训练模型及必要依赖未删除。三月七包是 RVC 格式，保留它不代表已接入 GPT-SoVITS。此前个人声音是参考音频零样本克隆，不应误称为训练出的权重。

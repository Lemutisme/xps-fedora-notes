# Dell XPS 13 的 Fedora 实践记录

在 **Dell XPS 13 DX13260 / SKU 0E53** 上完成的两个方案：内置扬声器修复，以及仅用于 GNOME 锁屏的红外人脸解锁。

验证日期：**2026-09-29**。这是特定机器、特定版本上的实际部署记录；文中的硬件映射需要在目标机器上重新确认。

| 方案 | 最终结果 | 文档 |
| --- | --- | --- |
| CS35L56 扬声器固件映射 | 重启后左右功放均报告 `Calibration applied`，实际播放恢复 | [音频修复](docs/audio.md) |
| Howdy + IR 摄像头 + GDM | 实际锁屏后无需输入密码即可解锁；保留密码回退 | [红外人脸解锁](docs/face-unlock.md) |

## 已验证环境

| 项目 | 值 |
| --- | --- |
| 机器 / BIOS | XPS 13 DX13260，SKU `0E53`，BIOS `1.7.3` |
| 系统 | Fedora Linux 45 Prerelease；系统发行标识为 Budgie，实际会话使用 GNOME / GDM |
| 内核 | `7.2.8-300.fc45.x86_64` |
| Secure Boot / SELinux | Enabled / Enforcing |
| 音频 | Intel SOF / SoundWire、Cirrus CS42L43、双 CS35L56 |
| PipeWire / WirePlumber | `1.6.9` / `0.5.17` |
| 固件包 | `cirrus-audio-firmware-20260916-1.fc45` |
| GDM | `51.0-1.fc45` |
| 系统 Python / Howdy 专用 Python | `3.15.0rc2` / Fedora `3.13.15` |
| 摄像头 | USB `0bda:55bc`；彩色 `/dev/video0`，IR `/dev/video2` |

## 附件

- [实测扬声器 ID 的读取工具](tools/read-speaker-id.py)
- [Howdy 仅限 GDM 已有桌面会话的补丁](patches/howdy-gdm-unlock-only.patch)
- [Howdy 配置示例](configs/howdy.ini)：默认禁用 PAM，先录入并验证
- [最小 SELinux 权限规则](configs/howdy_ir.cil)
- [Howdy 构建产物安装辅助工具](tools/install-howdy-artifacts.py)
- [第三方代码说明](THIRD_PARTY.md)

每篇文档都包含诊断依据、部署步骤、验证结果、适用限制和撤销方法。命令中的工作目录和用户名采用变量，按自己的机器调整。

Howdy 提供便利的人脸认证，但不能视为 Windows Hello 的等价安全实现。这里始终保留密码，并将启用范围限制为已有本地桌面会话的解锁。

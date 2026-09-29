# 第三方代码与来源

`patches/howdy-gdm-unlock-only.patch` 针对 [boltgolt/howdy](https://github.com/boltgolt/howdy) 的提交
`d3ab99382f88f043d15f15c1450ab69433892a1c`。补丁上下文及配置结构源自该项目，原项目 MIT 许可见 [LICENSES/Howdy-MIT.txt](LICENSES/Howdy-MIT.txt)。

Howdy、dlib、OpenCV、NumPy 和 dlib 预训练模型分别遵循各自的许可。本文的安装步骤从上游获取它们；仓库不分发其二进制构建产物和模型权重。

GDM 调用者会话的处理依据 [GNOME/gdm](https://github.com/GNOME/gdm) 的 `gdm-session-worker.c` 和 `gdm-manager.c`，文档链接回原项目。

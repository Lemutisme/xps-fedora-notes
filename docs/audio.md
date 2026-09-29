# 修复 XPS 13 DX13260 的内置扬声器

## 现象和定位

PipeWire、WirePlumber 正常运行，默认输出是 `sof-soundwire Speaker`，未静音；ALSA 也能识别声卡，但内置扬声器没有声音。

关键日志来自功放驱动：

```text
cs35l56 ... FIRMWARE_MISSING
cs35l56 ... Calibration disabled due to missing firmware controls
cs35l56 ... Can't read tuning IDs
```

检查命令：

```sh
wpctl status
aplay -l
journalctl -b -k --no-pager | rg 'cs35l56|cs42l43|sof-audio'
ls -l /usr/lib/firmware/cirrus/*10280e53*
```

该 SKU 的固件包提供 `spkid1`、`spkid2`、`spkid3`，没有 `spkid0`。本机 ACPI 的 `SWD6.AF01` 资源列出了 **GPI4 的 2、3 两个识别引脚**，但 `spk-id-gpios` 属性只映射了第一个。当前 `spi-cs42l43` 驱动因此只读取了型号的低位。

实测结果：

```text
gpiochip3: GPI4[2]=0, GPI4[3]=1
Speaker ID = 2
```

正确的两位数是 `0 | (1 << 1) = 2`，驱动只读低位则得到 `0`。这解释了为什么固件包齐全，功放却找不到适用固件。

## 确认适用条件

这不是对所有 XPS 都适用的固件替换。这里的映射只针对 **DX13260 / 0E53 / 实测 ID 2**，并且内核仍存在只读取低位的问题。

```sh
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/product_sku
cat /sys/class/dmi/id/bios_version
uname -r
sudo python3 tools/read-speaker-id.py
```

读取工具按这台机器的 ACPI 映射定位 GPIO 控制器，以输入方式读取两个引脚并释放句柄。它不写输出电平，不安装固件，也不修改驱动。其他 BIOS / 主板版本应先重新核对 ACPI；若读数不是 `0,1`，不要应用下面的 `0 → 2` 映射。

## 安装固件别名

保留发行版原有文件，在固件搜索路径的 `updates/cirrus` 目录中增加三个别名。以下代码在 Bash 中执行；若已有同名本地文件，应先检查其来源。

```bash
fw_root=/usr/lib/firmware
fw_prefix=cs35l56-b2-dsp1-misc-10280e53-spkid
for suffix in .wmfw.xz -ampl.bin.xz -ampr.bin.xz; do
    test -f "$fw_root/cirrus/${fw_prefix}2${suffix}" || exit 1
    test ! -e "$fw_root/updates/cirrus/${fw_prefix}0${suffix}" || exit 1
    test ! -L "$fw_root/updates/cirrus/${fw_prefix}0${suffix}" || exit 1
done
sudo mkdir -p "$fw_root/updates/cirrus"
for suffix in .wmfw.xz -ampl.bin.xz -ampr.bin.xz; do
    sudo ln -s "../../cirrus/${fw_prefix}2${suffix}" \
        "$fw_root/updates/cirrus/${fw_prefix}0${suffix}"
done
sudo restorecon -R "$fw_root/updates/cirrus"
```

对应关系：

| 驱动请求的别名 | 实际使用的发行版文件 |
| --- | --- |
| `...spkid0.wmfw.xz` | `...spkid2.wmfw.xz` |
| `...spkid0-ampl.bin.xz` | `...spkid2-ampl.bin.xz` |
| `...spkid0-ampr.bin.xz` | `...spkid2-ampr.bin.xz` |

`spkid2.wmfw.xz` 最终指向 `cs35l56/CS35L56_Rev4.5.9.wmfw.xz`。不能随意把型号 0 指向型号 1：调音文件还包含与扬声器硬件匹配的保护参数。

## 写入启动镜像并重启

新建 `/etc/dracut.conf.d/90-xps13-dx13260-audio.conf`：

```sh
# DX13260 / 0E53, measured speaker ID 2; affected driver reads bit 0 only.
install_items+=" /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0.wmfw.xz /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0-ampl.bin.xz /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0-ampr.bin.xz "
```

```sh
sudo restorecon /etc/dracut.conf.d/90-xps13-dx13260-audio.conf
sudo dracut --force --kver "$(uname -r)"
sudo lsinitrd "/boot/initramfs-$(uname -r).img" | rg '10280e53-spkid[02]|CS35L56_Rev4.5.9'
```

确认镜像包含三个别名、它们的目标文件，以及最终 `.wmfw.xz` 文件。然后保存工作并重启。该 dracut 配置也会用于后续内核的镜像生成。

本机尝试过在线解绑、重新绑定音频 PCI 控制器，出现大量 SoundWire 超时；声卡随后重新出现，但功放仍保留旧状态。因此这里采用重启流程，不把在线重载作为部署步骤。

## 验证结果

重启后执行：

```sh
journalctl -b -k --no-pager | rg 'cs35l56.*(Calibration|FIRMWARE_MISSING|tuning)'
wpctl status
```

2026-09-29 的实际结果：

```text
cs35l56 spi-cs35l56-right: Calibration applied
cs35l56 spi-cs35l56-left: Calibration applied
```

用户确认内置扬声器恢复播放。Secure Boot 保持开启；没有加载自编译内核模块。

## 撤销与后续维护

确认下面三个路径仍是本方案创建的 `spkid0 → spkid2` 符号链接，然后删除它们及本方案的 dracut 配置：

```bash
fw_root=/usr/lib/firmware/updates/cirrus
fw_prefix=cs35l56-b2-dsp1-misc-10280e53-spkid
for suffix in .wmfw.xz -ampl.bin.xz -ampr.bin.xz; do
    test "$(readlink "$fw_root/${fw_prefix}0${suffix}")" = \
        "../../cirrus/${fw_prefix}2${suffix}" || exit 1
done
for suffix in .wmfw.xz -ampl.bin.xz -ampr.bin.xz; do
    sudo rm -- "$fw_root/${fw_prefix}0${suffix}"
done
sudo rm -- /etc/dracut.conf.d/90-xps13-dx13260-audio.conf
sudo dracut --force --kver "$(uname -r)"
```

随后重启。如果其他已安装内核的 initramfs 也包含该别名，并且还准备启动它们，也应针对那些版本重新生成镜像。

升级到能正确读取两个 GPIO 的内核后，驱动应直接选择 `spkid2`。确认新内核的识别和音频正常后，可以撤销临时别名。

## 上游依据

- [Cirrus 提交的 DX13260 型号识别修复说明](https://lists.openwall.net/linux-kernel/2026/09/19/720)：解释了两位 GPIO 只映射一位的问题。
- [作者撤回通用补丁的后续说明](https://lkml.iu.edu/2609.3/04614.html)：计划改为机型专用处理。因此本记录没有宣称该补丁已合入，也没有安装该补丁。
- [Cirrus 对型号与调音文件的解释](https://lore-kernel.gnuweeb.org/linux-firmware/000b01dd3ac6%2439c46210%24ad4d2630%24%40opensource.cirrus.com/T/)：不能凭听感任意替换不同型号的参数。

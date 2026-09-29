# 使用 IR 红外摄像头解锁 GNOME 锁屏

## 完成后的行为

按 **Super+L** 锁屏，按空格展开解锁界面，看向摄像头即可识别。没有匹配到人脸或摄像头不可用时，回退到原来的密码认证；识别超时设为 8 秒。

范围限定为已有本地 GNOME 桌面会话的解锁。开机登录、sudo 和 SSH 没有启用 Howdy。2026-09-29 已完成真实锁屏测试，用户确认无需输入密码就解锁，GDM 审计记录也确认 `pam_howdy` 认证成功。

[Howdy 上游](https://github.com/boltgolt/howdy#readme) 明确说明其人脸认证不能等同于密码的安全强度。本方案使用红外通道，但不宣称具有 Windows Hello 的硬件信任链或同等抗冒用能力。

## 硬件与软件选择

本机摄像头 USB ID 为 `0bda:55bc`，包含两个图像接口：

| 节点 | 作用 | 格式 |
| --- | --- | --- |
| `/dev/video0` | 普通彩色摄像头 | MJPEG / YUYV，多种分辨率 |
| `/dev/video2` | IR 红外摄像头 | `GREY`，360×360，15 FPS |
| `/dev/video1`、`/dev/video3` | 元数据接口 | 不用于人脸图像采集 |

用以下命令自行确认接口：

```sh
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video2 --all --list-formats-ext
ls -l /dev/v4l/by-path/
```

配置采用稳定路径：

```text
/dev/v4l/by-path/pci-0000:00:14.0-usb-0:7:1.2-video-index0
```

在本机，直接采集 IR 图像可以得到正常照明和人脸检测，不需要另装 IR 发射器驱动。间隔出现黑帧是本次采集观察到的现象，Howdy 会跳过黑帧。

本机系统 Python 是 `3.15.0rc2`。检查过的 Fedora 45 Howdy COPR RPM 要求 Python ABI `3.14`，并存在 `keyboard`、`pyv4l2` 依赖缺口，无法直接安装。最终选择：

| 组件 | 固定版本 / 路径 |
| --- | --- |
| Howdy | 上游提交 `d3ab99382f88f043d15f15c1450ab69433892a1c` |
| 独立解释器 | Fedora Python `3.13.15` |
| 虚拟环境 | `/opt/howdy/venv` |
| dlib / NumPy / OpenCV headless | `20.0.1` / `2.2.6` / `4.12.0.88` |
| 认证模块 | `/usr/lib64/security/pam_howdy.so` |
| Python 代码 | `/usr/local/lib64/howdy` |
| 配置 / 人脸描述符 | `/etc/howdy/config.ini` / `/etc/howdy/models` |

## 构建与安装

以下是从已验证部署过程整理的重装步骤。安装辅助工具只负责复制选定构建产物；它是为文档整理的版本，未在当前已经配置好的系统上重新执行整套安装。原始构建、录入、权限配置和实际解锁均已验证。

从本仓库根目录开始，在普通用户的 Bash 中设置变量，后续只在需要时使用 sudo：

```bash
notes_dir="$(pwd)"
auth_user="$(id -un)"
work_dir="$(mktemp -d "$HOME/howdy-build.XXXXXX")"

sudo dnf install python3.13 python3.13-devel python3-devel \
    gcc-c++ cmake meson ninja-build inih-devel libevdev-devel pam-devel \
    systemd-devel v4l-utils policycoreutils-python-utils selinux-policy-devel

cd "$work_dir"
python3.13 -m venv build-env
build-env/bin/python -m pip wheel --wheel-dir=wheels \
    'dlib==20.0.1' 'numpy==2.2.6' 'opencv-python-headless==4.12.0.88'

sudo python3.13 -m venv /opt/howdy/venv
sudo /opt/howdy/venv/bin/python -m pip install --no-index \
    --find-links "$work_dir/wheels" \
    'dlib==20.0.1' 'numpy==2.2.6' 'opencv-python-headless==4.12.0.88'

git clone https://github.com/boltgolt/howdy.git howdy-source
git -C howdy-source checkout --detach d3ab99382f88f043d15f15c1450ab69433892a1c
git -C howdy-source apply "$notes_dir/patches/howdy-gdm-unlock-only.patch"

meson setup howdy-build howdy-source \
    --prefix=/usr/local --libdir=lib64 \
    -Dpam_dir=/usr/lib64/security \
    -Dconfig_dir=/etc/howdy \
    -Ddlib_data_dir=/usr/local/share/howdy/dlib-data \
    -Duser_models_dir=/etc/howdy/models \
    -Dpython_path=/opt/howdy/venv/bin/python \
    -Dinstall_pam_config=false -Dwith_polkit=false
meson compile -C howdy-build -j 2
```

dlib 的 wheel 编译需要一段时间，并会占用较多内存。这里使用 headless OpenCV，不需要安装 Howdy GTK 界面或 `pyv4l2` 录制后端。

获取预训练模型并校验：

```bash
mkdir -p "$work_dir/model-data"
for model in shape_predictor_5_face_landmarks dlib_face_recognition_resnet_model_v1 mmod_human_face_detector; do
    curl --fail --location \
        "https://raw.githubusercontent.com/davisking/dlib-models/master/${model}.dat.bz2" \
        --output "$work_dir/model-data/${model}.dat.bz2" || exit 1
done
(
    cd "$work_dir/model-data" || exit 1
    sha256sum -c "$notes_dir/configs/dlib-models.sha256" || exit 1
    bzip2 -dk ./*.dat.bz2
)

sudo python3 "$notes_dir/tools/install-howdy-artifacts.py" \
    "$work_dir/howdy-build" "$work_dir/model-data" "$notes_dir/configs/howdy.ini"
```

安装前检查配置示例的 `device_path` 确实指向自己的 IR 通道。该示例默认 `disabled = true`，此时尚未接入 GDM 认证。校验清单记录的是本次实际使用、且与上游 Git blob 核对一致的压缩模型文件；若上游文件更改导致校验失败，应先审查更新。

## 为什么需要 GDM 专用补丁

直接在通用 PAM 配置里添加 `auth sufficient pam_howdy.so` 会扩大启用范围。仅检查 `GDM_AUTH_SESSION_ID` 是否存在也不够，因为 GDM 的登录界面会话也可能出现在调用链中。

[附带补丁](../patches/howdy-gdm-unlock-only.patch) 增加 `gdm_reauth_only` 参数。启用此参数时，模块检查：

1. PAM 服务必须是 `gdm-password`，且没有远程主机。
2. GDM 提供的调用者会话 ID 必须存在。
3. libsystemd 查询到的会话所有者 UID 必须等于被认证用户。
4. 会话必须是本地 `user` 类，类型为 `wayland` 或 `x11`。

不满足条件则返回 `PAM_IGNORE`，继续原有密码栈。该判断针对已有本地桌面会话的 GDM 重新认证，并不单独查询“屏幕是否锁定”的状态。

补丁依赖 GDM 传递调用者会话信息的实现。参考 [GDM worker](https://github.com/GNOME/gdm/blob/main/daemon/gdm-session-worker.c) 和 [GDM manager](https://github.com/GNOME/gdm/blob/main/daemon/gdm-manager.c)。升级 GDM 大版本后应重新核对。

## 录入本人红外样本

打开摄像头遮挡，独自面对屏幕，保持正常使用距离。以下命令中的变量来自上面的普通用户 shell：

```sh
sudo /usr/local/bin/howdy -U "$auth_user" -y add 'XPS IR'
sudo /usr/local/bin/howdy -U "$auth_user" -y add 'XPS IR normal posture'
sudo chmod 700 /etc/howdy/models
sudo chmod 600 "/etc/howdy/models/${auth_user}.dat"
```

本次第一次样本能识别，但偶尔超时；补录正常坐姿后通过验证。最终匹配阈值仍为上游默认 `certainty = 3.5`，没有通过放宽阈值解决问题。

配置关闭了成功、失败抓拍。人脸描述符保存在本机 root 所有的目录内；模型权重与个人描述符是不同的数据。

可在接入 PAM 之前直接测试识别程序：

```sh
sudo /opt/howdy/venv/bin/python /usr/local/lib64/howdy/compare.py "$auth_user"
```

退出码 0 表示匹配成功。`disabled` 控制 PAM 模块，直接执行识别程序仍可用于部署验证。

## SELinux 最小权限修复

本机在 `xdm_t` 域中的认证测试出现：

```text
failed mmap(129600): errno=13 (Permission denied)
avc: denied { map } ... scontext=...:xdm_t:... tcontext=...:v4l_device_t:... tclass=chr_file
```

当时 Fedora 策略已允许其余所需摄像头操作，仅缺少视频缓冲区的 `map` 权限。安装本仓库规则：

```sh
sudo semodule -i "$notes_dir/configs/howdy_ir.cil"
getenforce
```

规则只有：

```text
(allow xdm_t v4l_device_t (chr_file (map)))
```

SELinux 保持 `Enforcing`。该规则作用于 `v4l_device_t` 类型的设备，不是只对 `/dev/video2` 的单独授权；Howdy 的配置负责选择 IR 通道。其他系统若出现不同拒绝，应根据对应操作审查，不直接套用所有审计日志生成宽泛放行规则。

## 接入 GDM，保留原有密码栈

本机 GDM 51 使用 `/usr/lib/pam.d/gdm-password-auth-substack`。先核对自己的版本：

```sh
cat /usr/lib/pam.d/gdm-password
cat /usr/lib/pam.d/gdm-password-auth-substack
```

原始 substack 内容如下：

```text
auth     include   password-auth
auth     required  pam_deny.so

password include   password-auth
password required  pam_deny.so
```

如果布局不同，应先适配自己的 GDM 配置。不要修改 authselect 自动生成的 `system-auth` / `password-auth`。

在确认没有已有 `/etc/pam.d/gdm-password-auth-substack` 自定义文件之后，备份并建立单服务覆盖：

```bash
test ! -e /etc/pam.d/gdm-password-auth-substack || exit 1
sudo install -d -m 700 /var/lib/howdy-local-backup
sudo cp /usr/lib/pam.d/gdm-password-auth-substack \
    /var/lib/howdy-local-backup/gdm-password-auth-substack.vendor
sudo cp /etc/howdy/config.ini /var/lib/howdy-local-backup/config.before-activation.ini
```

新建 `/etc/pam.d/gdm-password-auth-substack`，在完整保留原始内容的基础上，只增加这一条 `auth`：

```text
auth sufficient pam_howdy.so gdm_reauth_only
auth     include   password-auth
auth     required  pam_deny.so

password include   password-auth
password required  pam_deny.so
```

```sh
sudo chmod 644 /etc/pam.d/gdm-password-auth-substack
sudo restorecon /etc/pam.d/gdm-password-auth-substack
sudo /usr/local/bin/howdy disable false
authselect check
```

`sufficient` 使识别成功时完成这个子栈的认证；识别失败或被场景检查跳过时，继续已有密码流程。本机没有改动 sudo、SSH 或其他服务的 PAM 文件。

## 实际验证记录

| 检查 | 实际结果 |
| --- | --- |
| 未提供调用者会话的模拟初始登录 | 仅人脸认证被拒绝，PAM 返回认证失败 |
| 未录入的测试用户 | 被拒绝 |
| `manager` 类调用者会话 | 被拒绝 |
| 不存在的调用者会话 ID | 被拒绝 |
| 已录入用户的本地 GDM 重新认证 | 成功 |
| GDM 的 `xdm_t` 域中运行完整认证 | 添加 `map` 规则后成功，无新增 AVC 拒绝 |
| authselect 完整性检查 | valid |
| 实际 GNOME 锁屏 | 用户确认人脸解锁成功；`LockedHint` 恢复为 `no` |

测试中较早一次识别耗时约 3.8 秒；这是一次测量，不是延迟保证。真实锁屏最终出现的核心记录是：

```text
pam_howdy: Login approved
PAM:authentication grantors=pam_howdy,pam_gnome_keyring,pam_oo7
exe="/usr/libexec/gdm-session-worker" res=success
```

此表区分已执行的检查和代码中的限制：没有在真实登录界面注销再登录、远程桌面或所有其他用户组合上进行穷举测试。

## 撤销

先禁用 Howdy，然后确认 `/etc/pam.d/gdm-password-auth-substack` 仍仅包含本方案添加的那一行和原有 vendor 内容，再删除覆盖文件：

```sh
sudo /usr/local/bin/howdy disable true
sudo diff -u /usr/lib/pam.d/gdm-password-auth-substack /etc/pam.d/gdm-password-auth-substack
# 核对差异后：
sudo rm -- /etc/pam.d/gdm-password-auth-substack
sudo semodule -r howdy_ir
authselect check
```

删除覆盖文件后，PAM 自动使用 `/usr/lib/pam.d` 中的发行版配置。若文件已被其他工具或自己修改，先合并修改，不直接删除。

如需清除个人录入描述符，再执行：

```sh
sudo /usr/local/bin/howdy -U "$auth_user" clear
```

## 维护限制

- 本地编译的 Howdy 和 `/opt/howdy/venv` 中的 Python 包不会随 `dnf upgrade` 自动更新；需要定期审查、重建和验证。
- `/etc/pam.d` 中的本地覆盖会优先于发行版文件。GDM 升级后要检查 vendor substack 的变化。
- 补丁依赖 GDM 与 systemd 会话接口；相关升级后应重新验证“仅锁屏”限制。
- USB 接口路径或摄像头布局变化后，要重新确认配置中的 IR 通道。
- 如果关闭摄像头、盖上屏幕或识别失败，使用密码。即使 IR 识别成功，也不代表该方案具备专用活体检测能力。

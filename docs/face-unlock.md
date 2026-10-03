# Unlocking the GNOME lock screen with the IR camera

## Behavior after completion

Press **Super+L** to lock, press space to expand the unlock prompt, and look at the camera to be recognized. When no face matches or the camera is unavailable, it falls back to the original password authentication; the recognition timeout is 8 seconds.

The scope is limited to unlocking an existing local GNOME desktop session. Howdy is not enabled for boot-time login, sudo or SSH. A real lock-screen test was completed on 2026-09-29; the user confirmed unlocking without typing a password, and the GDM audit records confirm that `pam_howdy` authentication succeeded.

[Howdy upstream](https://github.com/boltgolt/howdy#readme) explicitly states that its face authentication must not be treated as strong as a password. This solution uses the infrared channel, but claims neither the Windows Hello hardware trust chain nor equivalent spoofing resistance.

## Hardware and software choices

The camera on this unit has USB ID `0bda:55bc` and exposes two imaging interfaces:

| Node | Role | Format |
| --- | --- | --- |
| `/dev/video0` | Regular color camera | MJPEG / YUYV, multiple resolutions |
| `/dev/video2` | IR camera | `GREY`, 360×360, 15 FPS |
| `/dev/video1`, `/dev/video3` | Metadata interfaces | Not used for face image capture |

Confirm the interfaces yourself with:

```sh
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video2 --all --list-formats-ext
ls -l /dev/v4l/by-path/
```

The configuration uses a stable path:

```text
/dev/v4l/by-path/pci-0000:00:14.0-usb-0:7:1.2-video-index0
```

On this unit, capturing IR images directly gives normal illumination and face detection, so no separate IR emitter driver is needed. Intermittent black frames were observed during this capture setup; Howdy skips black frames.

The system Python on this unit is `3.15.0rc2`. The Fedora 45 Howdy COPR RPM that was checked requires Python ABI `3.14` and has `keyboard` / `pyv4l2` dependency gaps, so it cannot be installed directly. Final choices:

| Component | Pinned version / path |
| --- | --- |
| Howdy | upstream commit `d3ab99382f88f043d15f15c1450ab69433892a1c` |
| Standalone interpreter | Fedora Python `3.13.15` |
| Virtual environment | `/opt/howdy/venv` |
| dlib / NumPy / OpenCV headless | `20.0.1` / `2.2.6` / `4.12.0.88` |
| Authentication module | `/usr/lib64/security/pam_howdy.so` |
| Python code | `/usr/local/lib64/howdy` |
| Configuration / face descriptors | `/etc/howdy/config.ini` / `/etc/howdy/models` |

## Build and install

The following are reinstallation steps organized from the verified deployment process. The installation helper only copies the selected build artifacts; it is a version tidied up for the documentation, and the full installation was not re-run on the already-configured system. The original build, enrollment, permission configuration and the actual unlock were all verified.

Starting from this repository root, set the variables in a normal user's Bash, and use sudo only where needed later:

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

The dlib wheel takes a while to compile and uses a fair amount of memory. Headless OpenCV is used here, so neither the Howdy GTK interface nor the `pyv4l2` recording backend is needed.

Fetch the pretrained models and verify them:

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

Before installing, check that `device_path` in the example configuration really points at your own IR channel. The example defaults to `disabled = true`, so GDM authentication is not hooked up at this point. The checksum list records the compressed model files actually used this time, cross-checked against the upstream Git blobs; if an upstream file change makes verification fail, review the update first.

## Why the GDM-specific patch is needed

Adding `auth sufficient pam_howdy.so` to a generic PAM configuration would widen the enabled scope. Only checking whether `GDM_AUTH_SESSION_ID` exists is not enough either, because GDM's login-screen session can also appear in the call chain.

The [bundled patch](../patches/howdy-gdm-unlock-only.patch) adds a `gdm_reauth_only` option. When enabled, the module checks:

1. The PAM service must be `gdm-password`, with no remote host.
2. The caller session ID provided by GDM must exist.
3. The UID of the session owner looked up via libsystemd must equal the user being authenticated.
4. The session must be of the local `user` class, of type `wayland` or `x11`.

If the conditions are not met, it returns `PAM_IGNORE` and the original password stack continues. This check targets GDM re-authentication of an existing local desktop session; it does not separately query "is the screen locked".

The patch depends on GDM's implementation of passing caller session information. Refer to the [GDM worker](https://github.com/GNOME/gdm/blob/main/daemon/gdm-session-worker.c) and [GDM manager](https://github.com/GNOME/gdm/blob/main/daemon/gdm-manager.c). Re-check after a major GDM upgrade.

## Enrolling your own infrared samples

Uncover the camera, sit alone in front of the screen, and keep your normal working distance. The variables in the commands below come from the normal user shell above:

```sh
sudo /usr/local/bin/howdy -U "$auth_user" -y add 'XPS IR'
sudo /usr/local/bin/howdy -U "$auth_user" -y add 'XPS IR normal posture'
sudo chmod 700 /etc/howdy/models
sudo chmod 600 "/etc/howdy/models/${auth_user}.dat"
```

The first sample recognized on this unit, but occasionally timed out; after adding a sample in a normal sitting posture, verification passed. The final matching threshold remained the upstream default `certainty = 3.5`; the problem was not solved by loosening the threshold.

The configuration disables success and failure snapshots. Face descriptors are stored in a root-owned directory on this machine; model weights and personal descriptors are different kinds of data.

You can test the recognition program directly before hooking it into PAM:

```sh
sudo /opt/howdy/venv/bin/python /usr/local/lib64/howdy/compare.py "$auth_user"
```

Exit code 0 means a match. `disabled` controls the PAM module; running the recognition program directly is still useful for deployment verification.

## Minimal SELinux permission fix

Authentication testing in the `xdm_t` domain on this unit showed:

```text
failed mmap(129600): errno=13 (Permission denied)
avc: denied { map } ... scontext=...:xdm_t:... tcontext=...:v4l_device_t:... tclass=chr_file
```

At the time, Fedora policy already allowed the remaining camera operations; only the `map` permission for video buffers was missing. Install the rule from this repository:

```sh
sudo semodule -i "$notes_dir/configs/howdy_ir.cil"
getenforce
```

The rule is only:

```text
(allow xdm_t v4l_device_t (chr_file (map)))
```

SELinux stays `Enforcing`. The rule applies to devices of the `v4l_device_t` type; it is not a separate grant for `/dev/video2` alone. Howdy's configuration is responsible for selecting the IR channel. On other systems, if different denials appear, review them per operation; do not blindly apply broad allow rules generated from all audit logs.

## Hooking into GDM while keeping the original password stack

GDM 51 on this unit uses `/usr/lib/pam.d/gdm-password-auth-substack`. Check your own version first:

```sh
cat /usr/lib/pam.d/gdm-password
cat /usr/lib/pam.d/gdm-password-auth-substack
```

The original substack content:

```text
auth     include   password-auth
auth     required  pam_deny.so

password include   password-auth
password required  pam_deny.so
```

If your layout differs, adapt to your own GDM configuration first. Do not modify the authselect-generated `system-auth` / `password-auth`.

After confirming there is no existing custom `/etc/pam.d/gdm-password-auth-substack`, back it up and create a single-service override:

```bash
test ! -e /etc/pam.d/gdm-password-auth-substack || exit 1
sudo install -d -m 700 /var/lib/howdy-local-backup
sudo cp /usr/lib/pam.d/gdm-password-auth-substack \
    /var/lib/howdy-local-backup/gdm-password-auth-substack.vendor
sudo cp /etc/howdy/config.ini /var/lib/howdy-local-backup/config.before-activation.ini
```

Create `/etc/pam.d/gdm-password-auth-substack`, keeping the original content fully intact and adding only this single `auth` line:

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

`sufficient` lets a successful match complete authentication for this substack; when recognition fails or the scenario check skips it, the existing password flow continues. No PAM files for sudo, SSH or other services were changed on this unit.

## Actual verification record

| Check | Actual result |
| --- | --- |
| Simulated initial login without a caller session | Only face authentication denied, PAM returns authentication failure |
| Test user without enrollment | Denied |
| `manager` class caller session | Denied |
| Non-existent caller session ID | Denied |
| Local GDM re-authentication of an enrolled user | Success |
| Full authentication run in GDM's `xdm_t` domain | Succeeded after adding the `map` rule, no new AVC denials |
| authselect integrity check | valid |
| Real GNOME lock screen | User confirmed face unlock succeeded; `LockedHint` returned to `no` |

One earlier recognition during testing took about 3.8 seconds; that is a single measurement, not a latency guarantee. The core record from the real lock screen in the end:

```text
pam_howdy: Login approved
PAM:authentication grantors=pam_howdy,pam_gnome_keyring,pam_oo7
exe="/usr/libexec/gdm-session-worker" res=success
```

This table distinguishes executed checks from limits in the code: no exhaustive testing was done for logging out and back in at the real login screen, remote desktop, or all other user combinations.

## Rollback

Disable Howdy first, then confirm that `/etc/pam.d/gdm-password-auth-substack` still contains only the line this procedure added plus the original vendor content, and remove the override file:

```sh
sudo /usr/local/bin/howdy disable true
sudo diff -u /usr/lib/pam.d/gdm-password-auth-substack /etc/pam.d/gdm-password-auth-substack
# After reviewing the diff:
sudo rm -- /etc/pam.d/gdm-password-auth-substack
sudo semodule -r howdy_ir
authselect check
```

After removing the override file, PAM automatically uses the distribution configuration in `/usr/lib/pam.d`. If the file has been modified by other tools or by yourself, merge the changes first instead of deleting it directly.

To also remove personal enrolled descriptors:

```sh
sudo /usr/local/bin/howdy -U "$auth_user" clear
```

## Maintenance limits

- The locally compiled Howdy and the Python packages in `/opt/howdy/venv` do not update with `dnf upgrade`; they need periodic review, rebuild and verification.
- Local overrides in `/etc/pam.d` take precedence over distribution files. Check vendor substack changes after a GDM upgrade.
- The patch depends on the GDM and systemd session interfaces; re-verify the "lock screen only" restriction after related upgrades.
- After the USB interface path or camera layout changes, re-confirm the IR channel in the configuration.
- If the camera is covered, the lid is closed, or recognition fails, use the password. Even successful IR recognition does not mean the solution has dedicated liveness detection.

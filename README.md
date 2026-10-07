# Fedora notes on the Dell XPS 13

Three solutions completed on a **Dell XPS 13 DX13260 / SKU 0E53**: a fix for the internal speakers, infrared face unlock limited to the GNOME lock screen, and stable automatic screen brightness on an ambient light sensor that reports garbage.

Verified on **2026-09-29** (audio, face unlock) and **2026-10-07** (brightness). This is a record of an actual deployment on one specific machine and release; the hardware mappings in these notes must be re-confirmed on the target machine.

[中文版 README](README.zh-CN.md) — the detailed guides in `docs/` are in English.

| Solution | Final result | Document |
| --- | --- | --- |
| CS35L56 speaker firmware mapping | After reboot both amplifiers report `Calibration applied`; real playback restored | [Audio fix](docs/audio.md) |
| Howdy + IR camera + GDM | Real lock screen unlocks without typing a password; password fallback kept | [Infrared face unlock](docs/face-unlock.md) |
| Ambient light sensor validation | Unusable readings are rejected and bucket changes confirmed before applying; offline replay of a 4-minute capture drops brightness changes from 119 to 2 | [Automatic brightness](docs/brightness.md) |

## Verified environment

| Item | Value |
| --- | --- |
| Machine / BIOS | XPS 13 DX13260, SKU `0E53`, BIOS `1.7.3` |
| System | Fedora Linux 45 Prerelease; the system edition identifies as Budgie, but the actual session uses GNOME / GDM |
| Kernel | `7.2.8-300.fc45.x86_64` (audio, face unlock); `7.2.9-300.fc45.x86_64` (brightness) |
| Secure Boot / SELinux | Enabled / Enforcing |
| Audio | Intel SOF / SoundWire, Cirrus CS42L43, dual CS35L56 |
| PipeWire / WirePlumber | `1.6.9` / `0.5.17` |
| Firmware package | `cirrus-audio-firmware-20260916-1.fc45` |
| GDM | `51.0-1.fc45` |
| System Python / Howdy-specific Python | `3.15.0rc2` / Fedora `3.13.15` |
| Camera | USB `0bda:55bc`; color `/dev/video0`, IR `/dev/video2` |
| Ambient light sensor | Intel ISHTP `8087:0AC2` via `hid_sensor_als`; ~40% of reports usable on kernel `7.2.8`, 100% on `7.2.9` |
| Automatic brightness | GNOME extension `adaptive-brightness@dmy3k.github.io` v30 |

## Extras

- [Tool to read the measured speaker ID](tools/read-speaker-id.py)
- [Patch restricting Howdy to GDM unlock of an existing desktop session](patches/howdy-gdm-unlock-only.patch)
- [Howdy configuration example](configs/howdy.ini): PAM disabled by default; enroll and verify first
- [Minimal SELinux allow rule](configs/howdy_ir.cil)
- [Helper to install the Howdy build artifacts](tools/install-howdy-artifacts.py)
- [Ambient light sensor health check](tools/als-health-check.py)
- [Third-party code notes](THIRD_PARTY.md)

Each document includes the diagnostic evidence, deployment steps, verification results, scope limits and rollback procedure. Working directories and user names in commands use variables; adjust them for your own machine.

Howdy provides convenient face authentication, but it must not be treated as a security-equivalent replacement for Windows Hello. The password is always kept, and the feature is limited to unlocking an existing local desktop session.

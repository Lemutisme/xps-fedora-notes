# Automatic screen brightness on a noisy ambient light sensor

Verified on **2026-10-07**. Machine: XPS 13 DX13260, SKU `0E53`, BIOS `1.7.3`,
kernel `7.2.9-300.fc45.x86_64`, GNOME `51`, `iio-sensor-proxy-3.9-3.fc45`.

The automatic brightness setup that was installed earlier (GNOME extension
`adaptive-brightness@dmy3k.github.io` v30, controlling the panel through
Mutter's `autoBrightnessTarget`) made the screen jump between very dark and
fully bright at random. This document records why, and what was changed.

The conclusion is not a better brightness curve. The sensor itself reports
garbage often enough that no curve can compensate, so the fix is to reject
unusable readings and to hold every change until it has been sustained.

## Symptom

Brightness swung between 1% and 100% with no relation to the room. Over one
four-minute capture the panel moved more than 5% of full scale **106 times**.

All measurements in the *Diagnostic evidence* and *Offline verification*
sections come from kernel `7.2.8-300.fc45.x86_64`. The later change on
`7.2.9-300.fc45.x86_64` is recorded under *The kernel version matters* — read
that section before concluding the patch is load-bearing.

## Diagnostic evidence

The extension logs nothing about why it moves, so the readings were captured
directly from the kernel and from D-Bus.

### The sensor is not two devices

`/sys/bus/iio/devices` exposes two `als` entries, `iio:device1` and
`iio:device2`. They are **two HID collections of one physical sensor**, not
two independent sensors, and cannot be swapped for one another:

| Device | Parent | Contents | `current_trigger` |
| --- | --- | --- | --- |
| `iio:device1` | `001F:8087:0AC2.0004/HID-SENSOR-200041.7` | illuminance, intensity, timestamp | *(empty)* |
| `iio:device2` | `001F:8087:0AC2.0004/HID-SENSOR-200041.8` | chromaticity, colour temp, illuminance | `als-dev2` |

`8087:0AC2` is the Intel ISHTP sensor hub, driven by `hid_sensor_als`. Only
`iio:device2` is actually claimed. Both report the same values.

At startup iio-sensor-proxy records:

```
Buffer '/dev/iio:device1' did not have data within 0.5s
```

### The scale is correct; the readings are not

`in_illuminance_scale` is `0.001`, so raw counts are micro-lux. iio-sensor-proxy
applies it faithfully — confirmed against its own debug strings:

```
Light read from IIO on '%s': %d (scale %lf) = %lf
```

Raw values divided by 1000 land squarely in the plausible indoor range
(9-18 lux in a dark room, 3000-8000 lux under a torch). Multiplied by the
scale as published they become 100000+ lux, which is brighter than direct
sunlight. So the scale is **not** the bug; individual samples are.

Sampling 225 consecutive reports classified as follows:

| Class | Count | Share | Test |
| --- | --- | --- | --- |
| `raw == 0`, report dropped | 78 | 34.7% | a genuinely dark room reads 9-18 lux, never 0 |
| `raw < 0` | 14 | 6.2% | illuminance cannot be negative; counts sit near the int32 limit |
| `raw >= 1e8` (~1e5 lux) | 32 | 14.2% | direct sunlight is ~1e5 lux; impossible indoors |
| **usable** | **89** | **39.6%** | — |

### The usable readings are good

Shining a torch on the sensor and moving it away produced a smooth curve:

```
t=196.6s  lux=3892 3520 3520 3483 3517 3517 3499 3499 3444 3440 3294 3269
          3127 3198 3044 3044 7702 8098 8098 8008 8008 7921 7921 7762 7675
          7801 6658 6658 5799 5827 5676 5393 5437 5274 5393 5214 5206 2877
```

That is a physically correct decay. The sensor works. Roughly 60% of the
time the value delivered is not a measurement.

### Why no bucket curve can fix it

The default buckets are

```
[(0,20,0.15), (5,200,0.25), (50,650,0.5), (350,2000,0.75), (1000,10000,1.0)]
```

`BucketMapper` keeps the current bucket while the value stays inside it, so
the effective switch points are 20 / 200 / 650 / 2000 lux. A corrupt sample
of 146844 lux or 0 lux is outside every bucket, so it always leaves the
current one and always triggers a switch. Upstream `SensorProxyService` has
only a 1 s throttle (`_throttleTimeoutMs = 1000`) and no validation, so each
corrupt sample is applied within about a second.

### No firmware fix available

`fwupdmgr get-updates` reports no updates for the system firmware; 1.7.3 is
current. The corruption is in the ISHTP transport, and the kernel passes the
bad values through unchanged.

### The kernel version matters, and it was not understood at first

All capture above was taken on kernel `7.2.8-300.fc45.x86_64`. After the patch
was deployed and the session was restarted on `7.2.9-300.fc45.x86_64`, the
same machine reported **128 of 128 samples usable (100%)** over 45 s, with
readings steady at 434-466 lux, and the panel did not move once in 150 s.

The cause of that change is **not established**. Candidates, none confirmed:

- an ISHTP transport fix between the two kernel builds;
- different ambient conditions (the first capture was at night, the second in
  daylight);
- something not yet ruled out.

So the patch's real-world benefit on this machine is **unproven**. What is
proven is that its logic is correct (the replay below) and that it does not
make things worse. It is worth keeping as insurance, not as a demonstrated
fix. Re-measure with `tools/als-health-check.py` after any kernel update.

## The change

Two layers, applied to the installed extension by
`patches/adaptive-brightness-als-validation.patch`.

### 1. Validate and smooth the input (`lib/SensorProxyService.js`)

Readings are checked against physical limits before they can affect
brightness:

| Constant | Value | Purpose |
| --- | --- | --- |
| `ALS_MIN_LUX` | 0.5 | 0 is a dropped report, not darkness |
| `ALS_MAX_LUX` | 20000 | above this the sensor is saturated |
| `ALS_MAX_RATE` | 3000 lux/s | rejects 13 → 200000 in one step |
| `ALS_WINDOW_MS` / `ALS_WINDOW_MAX` | 20000 ms / 7 | sliding median window |

Survivors enter a sliding window and the median is emitted, so an isolated
bad sample between good ones changes nothing. `lastLuxValue` now returns the
smoothed value; the `stats` getter exposes `{seen, accepted, rejected}`.

### 2. Confirm changes in bucket space (`lib/BrightnessConfirm.js`, new)

A change is applied only after the target bucket has been sustained:

| Setting | Value | Reason |
| --- | --- | --- |
| `darkenMs` | 2500 | darkening is confirmed fast; a dark room must not be left glaring |
| `brightenMs` | 8000 | brightening is confirmed slow; a false bright reading is what hurts |
| `cooldownMs` | 15000 | stops two adjacent buckets oscillating |

Confirmation runs **in bucket space, not lux space**, and this matters. An
earlier version compared the candidate lux value for equality, which meant a
smoothly decaying source (a torch being moved away) changed the candidate on
every sample and never satisfied the timer — the screen never moved at all.
Working on the discrete bucket means a drifting source is correctly treated
as one sustained intent. The class has no GNOME imports, so the policy is
testable on its own.

### 3. Close the validation bypass (`extension.js`)

Startup, resume, wake and bucket-settings changes called
`adjustBrightnessForLightLevel(sensorProxy.dbus.lightLevel, true)`, reading
the **raw** D-Bus value and applying it immediately — a corrupt sample at
resume would still flash the screen. These now read `lastLuxValue`, and reset
the confirmation clock since a wake is a legitimate reason to act at once.

## Verification

### On the live machine, after a session restart

| Measurement | Result |
| --- | --- |
| Panel moves over 5% in 60 s | **0** (235 samples) |
| Panel moves over 5% in 150 s | **0**, steady at 50% (96960/192000) |
| Sensor usable samples, 45 s | **128/128 (100%)**, 434-466 lux |
| Extension state | `ACTIVE`, no errors in the journal |

The steady 434-466 lux reading is itself notable: it is a plausible daytime
indoor figure, and it sat inside one bucket, so the confirmation stage
correctly produced no change at all.

### Offline, against the recorded bad capture

Replaying the real 240 s capture through the real patched classes, with a
virtual clock, against the real `BucketMapper`:

| | upstream | patched |
| --- | --- | --- |
| samples seen | 119 | 119 |
| accepted / rejected | 119 / 0 | 38 / 81 |
| brightness changes | 119 | **2** |
| range | 15% – 100% | 15% – 100% |
| steps over 2 points | **32** | **1** |

The two remaining changes are correct: `13 lux → 15%` at t=147 s, then
`3499 lux → 100%` at t=206 s when the torch was applied.

Synthetic scenarios with known-correct answers:

| Scenario | Expected | Result |
| --- | --- | --- |
| dark room, constant 20 lux, 120 s | stay at the bottom bucket | 1 change, then steady |
| 20 → 3020 lux over 180 s with a garbage spike every 10 s and a dropped report every 14 s | a few monotonic steps upward | 4 changes, monotonic: 153 → 387 → 787 → 2153 lux |
| 18 lux, torch on at 30 s, off at 90 s | exactly 2 changes | 2 changes, at t=42 s and t=97 s |

23 assertions on the gates and the confirmation policy pass, covering the
zero/negative/NaN/spike rejections, the rate-of-change rejection, median
resistance, asymmetric timing, cooldown release, and candidate restart.

## Scope and limits

- **The benefit of this patch on this machine is not demonstrated.** The
  problem it fixes was measured on `7.2.8-300.fc45.x86_64`; after the restart
  on `7.2.9-300.fc45.x86_64` the sensor reads 100% usable on its own. Keep it
  as insurance against the fault returning, not as a confirmed fix.
- **GNOME Shell caches extension JavaScript for the life of the process.**
  Editing files and running `gnome-extensions disable`/`enable` does **not**
  reload them, and the extension will report `ACTIVE` while still running the
  old code. A logout and login is required. This was verified by instrumenting
  the extension and observing that the instrumented code never ran despite
  reporting `ACTIVE`. Any future verification must confirm the process start
  time is later than the file modification time.
- The patch targets extension **v30** and is written against that tree. A
  version bump will likely need it re-applied by hand; `git apply --check`
  will say.
- Threshold values come from one machine plus a torch and a dark room. If the
  sensor's useful ceiling differs elsewhere, `ALS_MAX_LUX` is the value to
  revisit. Indoor lighting tops out well below 20000 lux.
- Correctness depends on usable samples arriving reasonably often. If a
  future firmware update leaves almost every sample unusable, brightness
  simply holds its last value rather than jumping — safe, but not automatic.
- When the sensor starves, brightness holds. It does not drift to the
  brightest setting.
- The jump to the top bucket has not been exercised on the live machine; it
  was verified only in the offline replay and in synthetic scenarios. A torch
  held on the sensor during normal use would confirm it.
- `docs/brightness.md` covers the panel only. The keyboard backlight is
  driven by the same bucket index and inherits the same filtering.
- An unrelated fault is visible in the journal and is **not** addressed here:
  `gsd-power: gsd_power_backlight_percentage_to_abs: assertion 'max > min' failed`,
  which makes the dimmed keyboard backlight fail to apply.

## Deployment

```bash
EXT="$HOME/.local/share/gnome-shell/extensions/adaptive-brightness@dmy3k.github.io"

# Back up the two files that change, plus the extension zip if present
cp -a "$EXT" "$EXT.bak"

cd "$EXT"
git apply --check /path/to/patches/adaptive-brightness-als-validation.patch
git apply /path/to/patches/adaptive-brightness-als-validation.patch
```

Then **log out and log back in**. This is not optional: GNOME Shell caches
extension JavaScript per process, so `disable`/`enable` will leave the old code
running while still reporting `ACTIVE`. On X11 the shell can be restarted
instead, but a logout is the reliable path on both sessions.

Verify that the new code is actually the code running, by comparing the shell
start time against the file modification time:

```bash
ps -o lstart= -p "$(pgrep -n gnome-shell)"
stat -c '%y' "$EXT/extension.js"
```

The first must be later than the second. If it is not, the patch is on disk
but not loaded.

Then check behaviour:

```bash
gnome-extensions info adaptive-brightness@dmy3k.github.io   # State: ACTIVE
python3 tools/als-health-check.py 60                       # usable share
```

Watch the panel under real light. It should move through the buckets over
several seconds, once per sustained change, and hold steady when the light has
not materially changed.

### Inspecting what the filter rejected

The service keeps `{seen, accepted, rejected}` counters, exposed as a `stats`
getter. There is no log output by default. If those counters are needed while
diagnosing, the cheapest check is the offline replay: record a capture with
`tools/als-health-check.py`, then confirm the thresholds against it.

## Rollback

```bash
EXT="$HOME/.local/share/gnome-shell/extensions/adaptive-brightness@dmy3k.github.io"
rm -rf "$EXT"
mv "$EXT.bak" "$EXT"
```

Then log out and back in. The original zip and the restore script from the
earlier install remain at
`~/.local/share/xps-adaptive-brightness/adaptive-brightness@dmy3k.github.io.shell-extension.zip`
and `~/.local/share/xps-adaptive-brightness/rollback.py`.

To stop using automatic brightness entirely instead of reverting:

```bash
gsettings set org.gnome.settings-daemon.plugins.power ambient-enabled true
gnome-extensions disable adaptive-brightness@dmy3k.github.io
```

## Files

- [Patch applied to the extension](../patches/adaptive-brightness-als-validation.patch)
- [Ambient light sensor health check](../tools/als-health-check.py)

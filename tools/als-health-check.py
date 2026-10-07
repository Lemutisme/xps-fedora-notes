#!/usr/bin/python3
"""Report the health of this laptop's ambient light sensor.

Reports what fraction of ambient light sensor readings are physically
plausible, so a corrupt reading can be told apart from a genuinely dark room.
It samples the kernel raw counter alongside the D-Bus LightLevel that
iio-sensor-proxy publishes, and classifies each observation.

Read the result together with the kernel version, because it matters a great
deal. On 7.2.8-300.fc45.x86_64 this machine produced roughly 60% unusable
samples (dropped reports, negative counts, saturation spikes) and this tool
reports 'too few usable readings'. On 7.2.9-300.fc45.x86_64 the same machine
reported 100% usable over a 45 s sample. See docs/brightness.md.

Run without root. Takes an optional duration in seconds (default 60).

While it runs, vary the light: cover the sensor with your hand, then shine a
torch at it. A working sensor produces a smooth curve. Dropout and saturation
counts are transport faults and are not affected by the light level, so a
sudden jump between consecutive readings points at the transport rather than
at the room.
"""
import dbus
import sys
import time
from pathlib import Path

SENSOR_HINT = (
    'the ambient light sensor is the small hole beside the webcam, '
    'on the top bezel'
)
# Real readings on this machine: ~9-18 lux in a dark room, and a smooth
# few-thousand-lux curve under a torch held close. The kernel multiplier is
# 0.001, so raw counts are micro-lux. See docs/brightness.md.
SCALE = 0.001
MIN_LUX = 0.5          # 0 means "no report arrived", not "pitch dark"
MAX_LUX = 20000        # above this the sensor is saturated, not bright
DEVICES = ('iio:device1', 'iio:device2')


def read_raw(device):
    p = Path('/sys/bus/iio/devices') / device / 'in_illuminance_raw'
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


def classify(raw, light_level):
    """Return (verdict, note) for one observation.

    The raw counter is judged in preference to LightLevel: iio-sensor-proxy
    republishes it on a 1 s throttle, so the two briefly disagree and the D-Bus
    value can still be zero while a perfectly good report has landed.
    """
    if raw is not None and raw < 0:
        return 'corrupt', 'negative raw count'
    if light_level is not None and light_level < 0:
        return 'corrupt', 'negative LightLevel'

    lux = raw * SCALE if raw is not None else light_level
    if lux is None:
        return 'dropped', 'no reading available'
    if lux == 0:
        return 'dropped', 'report reads zero'
    if lux > MAX_LUX:
        return 'saturated', 'implausible for an indoor reading'
    if lux < MIN_LUX:
        return 'dropped', 'below the plausible floor'
    return 'usable', ''


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0

    bus = dbus.SystemBus()
    proxy = bus.get_object('net.hadess.SensorProxy', '/net/hadess/SensorProxy')
    props = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    iface = dbus.Interface(proxy, 'net.hadess.SensorProxy')

    has_light = bool(props.Get('net.hadess.SensorProxy', 'HasAmbientLight'))
    print(f'HasAmbientLight: {has_light}')
    print(f'Sampling for {seconds:.0f}s. Vary the light during this run: {SENSOR_HINT}')
    print(f'\n{"t(s)":>7} {"LightLevel":>12} {"raw":>14} {"verdict":>10}  note')
    print('-' * 62)

    counts = {'usable': 0, 'dropped': 0, 'saturated': 0, 'corrupt': 0}
    usable = []

    iface.ClaimLight()
    try:
        start = time.time()
        seen = None
        while time.time() - start < seconds:
            level = float(props.Get('net.hadess.SensorProxy', 'LightLevel'))
            raw = None
            for device in DEVICES:
                candidate = read_raw(device)
                if candidate is not None:
                    raw = candidate if raw is None else max(raw, candidate)
            verdict, note = classify(raw, level)
            if (level, raw) != seen:
                print(f'{time.time() - start:7.1f} {level:12g} {str(raw):>14} '
                      f'{verdict:>10}  {note}', flush=True)
                seen = (level, raw)
            counts[verdict] += 1
            if verdict == 'usable':
                usable.append(raw * SCALE if raw is not None else level)
            time.sleep(0.25)
    finally:
        iface.ReleaseLight()

    total = sum(counts.values())
    print(f'\nobservations: {total}')
    for key in ('usable', 'dropped', 'saturated', 'corrupt'):
        share = counts[key] / total * 100 if total else 0
        print(f'  {key:<10} {counts[key]:5d}  ({share:5.1f}%)')
    if usable:
        usable.sort()
        print(f'\nusable lux range: {usable[0]:.0f} .. {usable[-1]:.0f}'
              f'   median {usable[len(usable) // 2]:.0f}')
    if usable and counts['usable'] / total > 0.3:
        print('\nVerdict: sensor is reporting usable data often enough for the')
        print('adaptive-brightness extension to work with validation in place.')
    else:
        print('\nVerdict: too few usable readings for automatic brightness.')
        print('Check docs/brightness.md for the fallback options.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

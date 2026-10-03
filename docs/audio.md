# Fixing the internal speakers on the XPS 13 DX13260

## Symptoms and diagnosis

PipeWire and WirePlumber were running normally, the default output was `sof-soundwire Speaker`, nothing was muted; ALSA also listed the sound card, but the internal speakers produced no sound.

Key logs came from the amplifier driver:

```text
cs35l56 ... FIRMWARE_MISSING
cs35l56 ... Calibration disabled due to missing firmware controls
cs35l56 ... Can't read tuning IDs
```

Diagnostic commands:

```sh
wpctl status
aplay -l
journalctl -b -k --no-pager | rg 'cs35l56|cs42l43|sof-audio'
ls -l /usr/lib/firmware/cirrus/*10280e53*
```

The firmware package for this SKU ships `spkid1`, `spkid2` and `spkid3`, but no `spkid0`. The ACPI `SWD6.AF01` resource on this unit lists **both identification pins 2 and 3 of GPI4**, but the `spk-id-gpios` property maps only the first one. As a result, the current `spi-cs42l43` driver reads only the low bit of the model ID.

Measured result:

```text
gpiochip3: GPI4[2]=0, GPI4[3]=1
Speaker ID = 2
```

The correct two-bit value is `0 | (1 << 1) = 2`; reading only the low bit gives `0`. This explains why the amplifier cannot find applicable firmware even though the firmware package is complete.

## Confirming applicability

This is not a firmware substitution that applies to every XPS. The mapping here is specific to **DX13260 / 0E53 / measured ID 2**, and only while the kernel still has the low-bit-only read problem.

```sh
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/product_sku
cat /sys/class/dmi/id/bios_version
uname -r
sudo python3 tools/read-speaker-id.py
```

The reading tool locates the GPIO controller according to this machine's ACPI mapping, reads the two pins as inputs and releases the handle. It does not drive output levels, install firmware, or modify the driver. On other BIOS / board revisions, re-check the ACPI tables first; if the readings are not `0,1`, do not apply the `0 → 2` mapping below.

## Installing the firmware aliases

Keep the distribution's original files and add three aliases in the `updates/cirrus` directory of the firmware search path. Run the following in Bash; if local files with the same names already exist, check where they come from first.

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

Correspondence:

| Alias requested by the driver | Distribution file actually used |
| --- | --- |
| `...spkid0.wmfw.xz` | `...spkid2.wmfw.xz` |
| `...spkid0-ampl.bin.xz` | `...spkid2-ampl.bin.xz` |
| `...spkid0-ampr.bin.xz` | `...spkid2-ampr.bin.xz` |

`spkid2.wmfw.xz` ultimately resolves to `cs35l56/CS35L56_Rev4.5.9.wmfw.xz`. Model 0 must not be pointed at model 1 arbitrarily: the tuning files also contain protection parameters matched to the speaker hardware.

## Writing into the boot image and rebooting

Create `/etc/dracut.conf.d/90-xps13-dx13260-audio.conf`:

```sh
# DX13260 / 0E53, measured speaker ID 2; affected driver reads bit 0 only.
install_items+=" /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0.wmfw.xz /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0-ampl.bin.xz /usr/lib/firmware/updates/cirrus/cs35l56-b2-dsp1-misc-10280e53-spkid0-ampr.bin.xz "
```

```sh
sudo restorecon /etc/dracut.conf.d/90-xps13-dx13260-audio.conf
sudo dracut --force --kver "$(uname -r)"
sudo lsinitrd "/boot/initramfs-$(uname -r).img" | rg '10280e53-spkid[02]|CS35L56_Rev4.5.9'
```

Confirm that the image contains the three aliases, their target files, and the final `.wmfw.xz` file. Then save your work and reboot. This dracut configuration is also used when generating images for future kernels.

On this unit, online unbind / rebind of the audio PCI controller was attempted and produced many SoundWire timeouts; the sound card reappeared afterwards, but the amplifiers kept their old state. The reboot procedure is therefore used here, and online reload is not offered as a deployment step.

## Verification results

After rebooting:

```sh
journalctl -b -k --no-pager | rg 'cs35l56.*(Calibration|FIRMWARE_MISSING|tuning)'
wpctl status
```

Actual result on 2026-09-29:

```text
cs35l56 spi-cs35l56-right: Calibration applied
cs35l56 spi-cs35l56-left: Calibration applied
```

The user confirmed that internal speaker playback was restored. Secure Boot stayed enabled; no self-compiled kernel modules were loaded.

## Rollback and ongoing maintenance

Confirm that the three paths below are still the `spkid0 → spkid2` symlinks created by this procedure, then delete them along with this procedure's dracut configuration:

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

Then reboot. If the initramfs of other installed kernels also contains this alias and you still plan to boot them, regenerate the images for those versions as well.

Once you upgrade to a kernel that correctly reads both GPIOs, the driver should select `spkid2` directly. After confirming that the new kernel detects the model correctly and audio works, the temporary aliases can be removed.

## Upstream references

- [Cirrus's explanation of the DX13260 model-ID fix](https://lists.openwall.net/linux-kernel/2026/09/19/720): explains the problem of two GPIO identification pins mapped to one bit.
- [Follow-up note withdrawing the generic patch](https://lkml.iu.edu/2609.3/04614.html): the plan changed to model-specific handling. This record therefore does not claim the patch has been merged, and the patch was not installed.
- [Cirrus's explanation of model IDs and tuning files](https://lore-kernel.gnuweeb.org/linux-firmware/000b01dd3ac6%2439c46210%24ad4d2630%24%40opensource.cirrus.com/T/): parameters for different models cannot be swapped based on how they sound.

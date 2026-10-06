# Compatibility

Pinefeat reverse-engineered Canon's lens protocol. It states that it cannot guarantee every lens works, because lens versions, firmware and electronics vary. CineMate adds a per-lens record of what works: [Capabilities](lenses.md#capabilities).

## Tested lenses

| Lens | Board lens ID | Iris | Focus | Notes | Tested on |
|---|---|---|---|---|---|
| Sigma 18-35mm f/1.8 DC HSM Art (Canon EF) | 112 | Only slightly | Not working | Iris: the board accepts every value from f/1.8 to f/22 and reports a short motor burst for each, but the iris moves only slightly across the whole range, in absolute and relative steps alike. The operator attributes this to the lens, not the adapter or CineMate. Focus: the board reports no focus position, always 0, so the board's own calibration finds a range of 0 to 0. The focus motor does not respond to the board's focus commands at all: 15 moves of +3000 showed no visible movement and the distance stayed at 0.28 m. Only the lens's own AF/MF self-test (switch flipped three times) moves focus. Under investigation with Pinefeat. **Treat this lens as unsupported for iris and focus; try another lens.** | CM4, imx477 on cam0, 2026-10-04 |

Reporting a lens that works, or does not, is welcome: [below](#reporting-a-lens).

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| State `absent`; no `IRIS` group | The board is not answering on the camera's I²C bus | Reseat the flat cables. The short cable goes into the board's **CAMERA** socket. The long one needs the contacts facing the way they do without the board. Wrong ports and shorted cables are the usual causes. |
| Still `absent` | Wrong port, or a bus problem | `sudo i2cdetect -l` lists the buses. Run `sudo i2cdetect -y <bus>` on each. The sensor shows at `1a` (or `UU`), the adapter at `0d`. |
| The camera disappeared after adding `dtoverlay=cef168` | Overlay loaded without `cef168.ko` for the running kernel | Remove the line from `/boot/firmware/config.txt` and reboot. Then [install the module](install.md#kernel-driver-level-optional). Check with `scripts/cef168-module-installed.sh`. |
| Overlay is in, camera is fine, no lens subdevice | The sensor word or the port in the overlay line is wrong | The port must match the sensor's line. The last word must be your sensor (`imx585` for mono too). See the [table](install.md#by-hand-step-by-step). |
| The camera does not register after a kernel update, and there is no `cef168` line in `config.txt` | Pinefeat's patched sensor overlay still declares the lens, and `cef168.ko` is not built for the new kernel | Rebuild the module with `sudo dkms autoinstall -k $(uname -r)`, or [undo Pinefeat's patch](install.md#undoing-pinefeats-installer) |
| State `no_lens` | No lens detected | Check the lens contacts and the mount. Try the lens's self-test: flip AF/MF three times. |
| State `unknown_lens` | A lens the database does not know | Name it and **Save as new**: [Lenses](lenses.md#saving) |
| Calibration says "set the lens to AF and try again" | Switch on MF. The gesture leaves it on the other side. | Switch to AF, press **Calibrate**: [Lenses](lenses.md#calibration) |
| Calibration finds a range of 0 to 0, or the position stays 0 | This lens reports no focus position, or its motor ignores the board (the Sigma above) | Iris still works. Save the lens with focus marked unsupported. Please [report the lens](#reporting-a-lens). |
| Iris command does not engage | Outside the range the lens accepts. The lens ignores such commands silently. | Enter the lens's [aperture range](lenses.md#aperture-range) |
| Iris shows an f-number the lens is not at | The lens cannot report its aperture. CineMate shows what it last sent. | Send a new value |
| Focus moves in one direction only | Likely the board thinks it is at an end of its range | [Calibrate](lenses.md#calibration) |
| Kernel driver gone after a kernel update (Pi 4B, CM4) | No headers for the new kernel, so DKMS did not rebuild | `sudo apt install linux-headers-rpi-v8`, then `sudo dkms autoinstall -k $(uname -r)` and reboot |

## Reporting a lens

Send Pinefeat and the CineMate project:

| What | How |
|---|---|
| Lens make, model and mount | Printed on the lens |
| Lens ID | Shown in the **Lens / Pinefeat** pane |
| What works | Iris and focus: yes, no, or partly |
| The adapter's raw data | See below |
| The calibration log | See below |

The raw data needs the optional kernel driver. Find the lens device as in [Installation](install.md#by-hand-step-by-step), step 8, then:

```bash
v4l2-ctl -d $DEV_LENS --get-ctrl data
```

The calibration log uses Pinefeat's own tool, which the CineMate install does not build:

```bash
cd ~/cef168
g++ -Wall -Wextra -o calibrate calibrate.cpp
./calibrate -d $DEV_LENS -v
```

Run it with the lens switch on **AF**. Without the driver, send the lens ID and the message line from the **Lens / Pinefeat** pane instead.

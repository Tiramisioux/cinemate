---
datum: 2026-07-22 22:34:03
kontext: Projekt
projekt: "#CINEMATE"
fritext: kernel_drivers_dtoverlays
typ: ""
källa: cinepi-raw / cinemate / libcamera källkod
type: projektplanering
ursprung: dev-notes/image-pipeline-explained
samling: Image pipeline
---

# Kernel, drivers and dtoverlays

> [!info] Image pipeline — 4-delad guide
> 1. [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|The image pipeline: sensor to storage]]
> 2. **Kernel, drivers and dtoverlays** *(denna not)*
> 3. [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files explained]]
> 4. [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|Case study: ClearHDR on the IMX585]]
>
> *Revised 2026-09-02 after an adversarial source-code review.*

Why the camera exists to the Pi at all, and why the kernel version decides which features work. This article sits under the [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|image pipeline guide]] and explains the layer the pipeline stands on — the one you touch through `config.txt` and `apt`.


## What the kernel does for the camera

Three words get used loosely; keep them apart:

| Term | Meaning |
|------|---------|
| **Driver** | kernel code that knows how to talk to one device — a sensor over I2C |
| **Module** | a driver compiled as a loadable file (`.ko`) instead of built into the kernel |
| **Subsystem** | the shared framework drivers plug into — here **V4L2** (Video4Linux2) and the **Media Controller** |

The camera surfaces as two kinds of device node:

- `/dev/video*` — on the Pi 5 these are the CFE's nodes from [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|Stage 3]]. The raw-Bayer and statistics nodes are **capture** nodes (DMA endpoints the hardware writes into); the **configuration** node runs the other way — it is a metadata *output* node that userspace queues Front End settings into each frame.[^cfe]
- `/dev/v4l-subdev*` — **sub-device** control nodes: the sensor itself, the CSI-2 receiver, the Front End. Exposure, gain, and the HDR control are set on the **sensor subdev**.

The **Media Controller** ties them into a graph: sensor subdev → CSI-2 → CFE capture node. `media-ctl -p` prints that graph.

---

## Device tree and overlays

The Pi cannot probe an I2C camera the way it probes a USB device. Nothing on the bus announces "I am an IMX585 at address 0x1a." The kernel has to be **told** — before boot — that a sensor exists, where, and how it is wired. That description is the **device tree**, and a camera adds itself with a **device-tree overlay** loaded from `config.txt`.

The best way to understand overlays is to read the real one. Here is the IMX585 overlay the driver ships, annotated.[^overlaysrc]

### The sensor node

```dts
cam_node: imx585@1a {
    compatible = "sony,imx585";
    reg = <0x1a>;                          // I2C address 0x1a
    clocks = <&cam1_clk>;
    assigned-clock-rates = <24000000>;     // 24 MHz input clock
    ...
    port {
        cam_endpoint: endpoint {
            link-frequencies = /bits/ 64 <720000000>;   // default 720 MHz link
        };
    };
};
```

Every fact the kernel needs is here:

- `imx585@1a` / `reg = <0x1a>` — the **I2C address**.
- `compatible = "sony,imx585"` — the **match string**. The kernel driver binds to a node whose `compatible` it recognises; libcamera's sensor helper registers under the same name.[^register]
- `clocks` / `assigned-clock-rates` — the **24 MHz** input clock (one of the clock options the driver accepts).
- `link-frequencies` — the **default CSI-2 link speed**, 720 MHz.

### Lanes, and the two fragments

```dts
fragment@0 { target = <&cam_endpoint>; __overlay__ { data-lanes = <1 2 3 4>; }; };  // active
fragment@1 { target = <&cam_endpoint>; __dormant__ { data-lanes = <1 2>;     }; };  // dormant
```

The overlay ships with **4-lane wiring as the live default** and a 2-lane version held dormant.[^overlaysrc] More lanes means more CSI-2 bandwidth, which is why the IMX585 can drive 4K at frame rates the 2-lane IMX477 cannot.

### The `__overrides__` block = the `config.txt` parameters

```dts
__overrides__ {
    2lane = <0>, "-0+1-2+3";              // switch to 2 lanes
    cam0  = ... retarget everything to cam0 ...
    mono  = <&cam_node>,"mono-mode:0=1";
    ccmp  = <&cam_node>,"sony,clearhdr-ccmp?";   // cinemate-7modes: opt into 12-bit CCMP ClearHDR
    ...
};
```

This block defines the parameters you append after the overlay name — and *only* these names are valid parameters. So:

- `dtoverlay=imx585` → cam1, 4 lanes, 720 MHz (the defaults; cam1 **is** the default, there is no `cam1` parameter).
- `dtoverlay=imx585,cam0` → the `cam0` override retargets every fragment (I2C bus, CSI port, clock, regulator) to the other connector.
- `dtoverlay=imx585,2lane` → disables the 4-lane fragments, enables the 2-lane ones.
- `dtoverlay=imx585,mono` → the mono variant on the default connector.
- `dtoverlay=imx585,ccmp` → enables 12-bit companded ClearHDR (default-on for colour; opt-in on mono) on the `cinemate-7modes` driver.

> [!warning] There is no `,cam1` parameter
> cam1 is the untyped default, so a line like `dtoverlay=imx585,cam1,mono` hands the firmware an unknown parameter — which it normally rejects, and that can keep the whole overlay from applying at boot. Write `dtoverlay=imx585,mono` instead. (Whether the firmware rejects or silently ignores it deserves a boot test; either way the parameter does not exist.)

> [!info] Why the camera 'doesn't exist' without an overlay
> With no overlay, nothing instantiates a `sony,imx585` at 0x1a on the CSI bus. No sensor subdev is created, no `/dev/video` capture appears, and `rpicam-hello --list-cameras` shows nothing. The overlay is the thing that makes the camera real to Linux.

### In `config.txt`

The clean-install default is the HQ Camera on connector 0. Each sensor's section in the managed block carries its own `camera_auto_detect` line, because the right value differs per sensor:[^configtxt]

```ini
camera_auto_detect=1
dtoverlay=imx477,cam0
#dtoverlay=imx296,cam0
## for the out-of-tree sensors, switch auto-detect off:
#camera_auto_detect=0
#dtoverlay=imx283,cam0
#dtoverlay=imx585,cam0
#dtoverlay=imx585,mono
```

You uncomment that sensor's section, set the connector, and reboot. For the in-tree, auto-detectable sensors (imx477, imx296) the installer keeps `camera_auto_detect=1`; for the out-of-tree imx283/imx585 it sets `camera_auto_detect=0` so the Pi's auto-probe doesn't fight the manual overlay.

---

## A sensor driver's job

Once bound, the kernel driver does three things:

1. **Publishes the mode table** — the resolutions and bit depths, as V4L2 formats and frame sizes. This is the `supported_modes[]` array from the [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|sensor stage]].
2. **Exposes V4L2 controls** — typically exposure, analogue gain, vertical/horizontal blanking, flips, sometimes digital gain and a test pattern, and, for HDR sensors, `V4L2_CID_WIDE_DYNAMIC_RANGE`. (The exact set varies: the imx585 driver exposes no digital-gain control, and gained a test-pattern control only on `cinemate-7modes`.)
3. **Translates control writes into I2C register sequences** — a new exposure becomes writes to the SHR/VMAX registers; a new gain becomes a write to the gain register.

The two Cinemate example sensors ship in **opposite ways**, and that difference drives most of this article:

| | IMX477 | IMX585 |
|---|---|---|
| Where the driver lives | **in-tree**: `drivers/media/i2c/imx477.c`, inside the Raspberry Pi kernel | **out-of-tree**: a separate `imx585-v4l2-driver` repo |
| How it is installed | ships with the kernel, always matched to it | **DKMS** module, compiled against the running kernel[^dkms] |
| Kernel requirement | whatever kernel you run | **6.12 or newer**[^driverreadme] |
| Risk on kernel update | none | must rebuild; an API change can break the build |

**DKMS** (Dynamic Kernel Module Support) is the system that rebuilds an out-of-tree module whenever the kernel changes. The IMX585 driver installs through it: `apt install linux-headers dkms git`, then a build script.[^driverreadme]

---

## Kernel versions and why they matter to the pipeline

This is the part that pays off when you add features like HDR.

**In-tree drivers move with the kernel. Out-of-tree drivers do not.** An out-of-tree driver is compiled against one kernel's headers. When a kernel API changes — the sub-device API, the register-access helpers — an older driver branch can simply stop building. The upstream will127534 repos carry kernel-version branches for exactly this reason (imx585: `main`/`6.12.y`/`6.6.y`/`6.1.y`; imx283: `master`/`6.12.y`/…), and a branch written for a pre-6.8 kernel API will not compile on 6.12. The **Tiramisioux fork Cinemate installs from** is a step further along: its supported branches are feature-named — the installer defaults to `innomaker-v1.0`, and current development happens on `cinemate-7modes` — with `6.12.y` kept as the legacy snapshot ("no longer the supported default", per the installer).[^branches]

To keep this from breaking your camera, **the Cinemate installer pins a kernel baseline**. The current pin is `6.12.93+rpt-rpi-2712`, with matching `linux-image` and `linux-headers` packages and a rollback directory.[^pin] This stops an `apt` upgrade from silently moving the kernel out from under the out-of-tree driver.

### Kernel version can gate a whole feature

The headline example: **ClearHDR 16-bit did not work until a kernel fix**. The Front End (rp1-cfe) had two 16-bit handling fixes that the project's *earlier* pinned kernel, 6.12.25, predated. On that kernel, 12-bit capture was fine but every 16-bit capture came out as garbage — on every driver and every app. The fix was not application code; it was **upgrading the kernel** and rebuilding the DKMS sensor modules. The supported baseline is now **6.12.93+rpt** — chosen precisely because it contains both fixes — and that is why the installer pins it. (The bring-up notes' working reference image ran 6.12.75; treat that as history, not as the supported minimum.)[^hdrkernel]

> [!note] The lesson
> When a new imaging feature "doesn't work," the cause can live below the driver, in the kernel's camera front-end code. The layer you can change fastest (app code) is not always the layer at fault. The [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|ClearHDR case study]] tells this story in full.

The exact pinned version is a moving target set in `cinemate-install.sh`; check it there rather than trusting a number in a doc.

---

## Seeing it live

A short toolkit for inspecting the stack on the Pi:

| Command | Shows |
|---------|-------|
| `uname -r` | the running kernel (must be 6.12+ for the IMX585; 6.12.93+rpt for 16-bit ClearHDR) |
| `dmesg \| grep -i imx585` | driver probe, and the mode-table log lines (`Update minimum HMAX…`, `Framing: VMAX=…`) — also the reliable way to confirm your overlay loaded |
| `ls /proc/device-tree/` + `media-ctl -p` | the applied device tree and the media graph: sensor → CSI-2 → CFE |
| `v4l2-ctl --list-devices` | the `/dev/video*` and `/dev/v4l-subdev*` nodes |
| `v4l2-ctl -d /dev/v4l-subdevN --list-ctrls` | the sensor's controls, including `wide_dynamic_range` |
| `rpicam-hello --list-cameras` | libcamera's view — detected sensor and its plain modes and bit depths |

Two traps worth naming:

- **`dtoverlay -l` will not show your camera overlay.** It lists only overlays applied at *runtime* by the `dtoverlay` utility; an overlay applied by the firmware from `config.txt` is "baked in" and prints as `No overlays loaded` even on a perfectly working camera. Verify with `dmesg`, `/proc/device-tree`, or the media graph instead.[^dtoverlayl]
- **Cinemate's live mode table does not come from `rpicam-hello`.** Cinemate probes with `cinepi-raw --list-cameras`, run *twice* — plain, and with `--hdr sensor` — and merges the results, so the ClearHDR-only modes appear only in the second probe.[^listcameras] `rpicam-hello --list-cameras` is a fine sanity check for the plain modes, but a mode missing there is not necessarily missing downstream. (Run it while cinepi-raw is stopped; the camera is single-owner.)

---

## Recap

- A camera becomes real to Linux only via a **device-tree overlay** loaded from `config.txt`; the overlay carries the I2C address, CSI port, clock, and lanes.
- The `__overrides__` block in the overlay defines the `,cam0` / `,2lane` / `,mono` / `,ccmp` parameters you type — and nothing else; there is no `,cam1`.
- **IMX477 is in-tree** (moves with the kernel); **IMX585 is an out-of-tree DKMS module** needing kernel 6.12+.
- The installer **pins a kernel baseline** (currently 6.12.93+rpt) so an out-of-tree driver keeps building — and, for ClearHDR, so the Front End's 16-bit fixes are present.
- A **kernel version can gate a pipeline feature** — ClearHDR 16-bit is the proof.

Continue with [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files explained →]].

---

## Footnotes

[^cfe]: Raspberry Pi PiSP Camera Front End (rp1-cfe) — Linux kernel docs: <https://docs.kernel.org/admin-guide/media/raspberrypi-rp1-cfe.html> (mainline 6.13+ doc; the `rpi-6.12.y` tree carries the driver but not this page). Node directions: `rp1_cfe/cfe.c` registers `fe_config` as `V4L2_CAP_META_OUTPUT` with a source pad.
[^overlaysrc]: `imx585-v4l2-driver/imx585-overlay.dts` — sensor node `imx585@1a`, `reg = <0x1a>`, `link-frequencies = <720000000>`, `fragment@0` (`data-lanes = <1 2 3 4>` live) vs `fragment@1` (`<1 2>` dormant), and the `__overrides__` block (`2lane`, `cam0`, `mono`; `ccmp` on `cinemate-7modes`).
[^register]: `libcamera/src/ipa/rpi/cam_helper/cam_helper_imx585.cpp` — `RegisterCamHelper reg("imx585", …)`; the kernel driver binds via its `of_match` on `sony,imx585`.
[^configtxt]: Cinemate Switching sensors (`docs/config-txt.md`) + `cinemate-install.sh` — clean-install default `camera_auto_detect=1` + `dtoverlay=imx477,cam0`; the installer's per-sensor sections set `camera_auto_detect` to 1 for imx477/imx296 and 0 for imx283/imx585.
[^dkms]: `imx585-v4l2-driver/README.md` — DKMS install adapted from the CM4 carrier project; requires `linux-headers`, `dkms`, `git`.
[^driverreadme]: `imx585-v4l2-driver/README.md` — "You should be running on a Linux kernel version 6.12 or newer."
[^branches]: `git ls-remote` on Tiramisioux/imx585-v4l2-driver: branches `6.12.y`, `cinemate-7modes`, `innomaker-v1.0`; `cinemate-install.sh` defaults `IMX585_DRIVER_REPO_REF` to `innomaker-v1.0` ("the old 6.12.y branch … is no longer the supported default"). Upstream kernel-version branches: will127534/imx585-v4l2-driver (`main`, `6.12.y`, `6.6.y`, `6.1.y`), will127534/imx283-v4l2-driver (`master`, `6.12.y`, …).
[^pin]: `cinemate-install.sh` — `KERNEL_BASELINE_ABI_2712=6.12.93+rpt-rpi-2712` with matching `linux-image`/`linux-headers` packages and `KERNEL_ROLLBACK_DIR`; the installer comment names 6.12.93 as the oldest baseline validated for imx585 ClearHDR. The previous pin was 6.12.25.
[^hdrkernel]: `innomaker585/CLEARHDR-STATE.md` (author-local notes, not in any repo) — root cause traced to rp1-cfe kernel fixes (2025-06-27 "Avoid unpack operation for 16-bit formats", 2025-07-04 "Workaround for 16-bit mismatch"); the earlier 6.12.25 pin predates both. Supported minimum per `docs/clear-hdr.md` and `docs/installation-steps.md`: ≥ 6.12.93+rpt.
[^dtoverlayl]: Raspberry Pi configuration docs: an overlay applied by the firmware "becomes 'baked in' such that it won't be listed by `dtoverlay`"; the utility tracks only its own runtime state under `/tmp/.dtoverlays`.
[^listcameras]: Cinemate `src/module/sensor_detect.py` — builds `cinepi-raw --list-cameras`, runs it plain and with `--hdr sensor`, and merges the two mode lists; see Camera sensors and frame rates.

---
#CINEMATE #IMAGE_PIPELINE_MAP

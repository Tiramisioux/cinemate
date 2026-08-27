# Overclocking the Pi

Raise the Raspberry Pi 5 RP1 image-pipeline clock to unlock higher imx585
ClearHDR frame rates. **Pi 5 and CM5 only** — the RP1 southbridge does not
exist on the Pi 4 family, so none of this applies there.

Instructions courtesy of **Will Whang**, with thanks. See his work at
[github.com/will127534](https://github.com/will127534).

!!! warning "Pi 5 / CM5 only"
    Do not apply these steps on a Pi 4 / 400 / CM4. The device-tree overlay
    targets the RP1 (`brcm,bcm2712`) and the libcamera change assumes the PiSP
    (Pi 5) pipeline. Everything the installer does here is gated on that same
    `bcm2712` check, so a Pi 4 install simply skips it.

## What it does

| Change | Stock | Overclocked |
|---|---|---|
| RP1 `PLL_SYS` / `CLK_SYS` | 200 MHz | **333.33 MHz** (the overlay asks for 300) |
| PiSP pixel-rate ceiling | 380 MPix/s | 580 MPix/s |

The overlay raises the clock. The pixel-rate ceiling tells libcamera how much
the pipeline can actually drain, and Cinemate sets it to match. Both are
needed, and they must agree — see [How it works](#how-it-works).

## What the Cinemate install ships

`cinemate-install.sh` does all of this automatically on a Pi 5 / CM5. You do
not need the manual steps at the end of this page unless you are building the
stack by hand:

| Step | Installer function | Result |
|---|---|---|
| Compile + install the overlay | `configure_rp1_overclock` | `/boot/firmware/overlays/rp1-overclock.dtbo` |
| Add the config.txt line | `configure_boot_config` | `#dtoverlay=rp1-overclock`, **commented out** |

The overclock therefore ships **installed but off**. Stock clocks stay the
default; you opt in. The pixel-rate ceiling needs no install step — Cinemate
works it out at every launch from whether the overlay is enabled.

### Switching it on and off

Use the **Boot config** pane of the settings editor at
`http://cinepi.local:5000/settings-editor`. The **RP1 overclock** toggle
comments and uncomments the overlay line for you.

!!! warning "Both directions need a reboot"
    The RP1 clock is set from the device tree at boot, so nothing changes
    until the Pi restarts — switching **on** and switching **off** both
    require it. Restarting Cinemate alone does not pick it up. Saving from
    the settings editor reboots for you (**Save & reboot Pi**, roughly 25
    seconds); from a shell you reboot yourself.

The toggle only appears on a `bcm2712` board whose `config.txt` already
contains the overlay line. If it is missing, re-run `cinemate-install.sh` to
add it. See [Modifying config.txt](config-txt.md) for the file itself.

Equivalent from a shell:

```bash
sudo sed -i 's/^#\s*dtoverlay=rp1-overclock/dtoverlay=rp1-overclock/' /boot/firmware/config.txt
sudo reboot
```

To go back to stock, re-comment the line and reboot.

## Link frequency

Two different ceilings, and you need both raised:

| Raises | Setting |
|---|---|
| What the **sensor sends** | CSI-2 link frequency, a parameter on the sensor's overlay line |
| What the **receiver takes** | the RP1 overclock on this page |

A stock RP1 tops out near 43.8 fps at 4K no matter what the sensor is told to
do, which is why the link-frequency menus appear once the overclock is on.
Each port has its own — cam0 and cam1 are independent. Cinemate writes the
parameter only when it differs from the sensor's default:

```
dtoverlay=imx585,cam0,link-frequency=1039500000
```

Per-sensor values live in `resources/sensors.json`. That file is the source of
truth — the menu, the validation and the tables below all read from it. See
[Sensors](sensors.md) for the full per-sensor tables.

### imx585

| Value | Mbps/lane | 4K 12-bit, 4 lanes |
|---|---|---|
| 297 MHz | 594 | 20.8 fps |
| 360 MHz | 720 | 25.0 fps |
| 445.5 MHz | 891 | 30.0 fps |
| 594 MHz | 1188 | 41.7 fps |
| **720 MHz** (default) | 1440 | 50.0 fps |
| 891 MHz | 1782 | 60.0 fps |
| 1039.5 MHz | 2079 | 75.0 fps |

Halve for 2-lane, halve again for ClearHDR, double for 2×2 binned. Figures
come from [will127534/imx585-v4l2-driver](https://github.com/will127534/imx585-v4l2-driver)
and are advisory until measured on this stack. The driver also defines
1188 MHz (2376 Mbps/lane); Cinemate does not offer it — the Pi 4 cannot use it
and the Pi 5 drops frames.

### imx283

360 MHz (720 Mbps/lane) and **720 MHz** (1440 Mbps/lane, default). Sony ships
exactly two register sequences and the driver rejects anything else.

!!! note "720 MHz is already the ceiling here"
    The only selectable alternative is *slower*. This closes the standing
    question of whether a faster link would lift the 4K modes past their
    44/41 fps: it would, but no faster link exists. More frame rate on the
    imx283 means a lower bit depth, not a faster link.

    Selecting a non-default value needs the `link-frequency` overlay
    parameter, which exists only in `Tiramisioux/imx283-v4l2-driver` `6.12.y`
    at `257c9cf` or later. An older overlay rejects the unknown parameter and
    the camera will not enumerate at all — re-run the installer first.

### The others

| Sensor | Link | Menu |
|---|---|---|
| imx477 | 450 MHz default; since kernel 6.12.49 the driver computes PLL settings for any ~3 MHz multiple | **not yet** — values recorded, menu held back pending hardware verification |
| imx296 | fixed 594 MHz, 1 lane; the 60 fps cap is readout-limited, not link-limited | no |
| imx519 | fixed 408 MHz; the driver rejects anything else at probe | no |

### Receiver ceilings

| Receiver | Spec | Observed |
|---|---|---|
| Pi 5 / CM5 (RP1) | 1.5 Gbps/lane | 1782 Mbps/lane fine, 2079 works, 2376 drops frames. Separate drain limit: 380 MPix/s stock, 580 with the overclock |
| Pi 4 / CM4 (Unicam) | none published | ~1.4 Gbps/lane; SDRAM-bandwidth-limited; 2376 fails |

## How it works

Two independent limits, and raising one without the other buys nothing:

| Limit | What it caps | Raised by |
|---|---|---|
| CSI-2 link frequency | how fast the **sensor sends** | a parameter on the sensor's overlay line |
| PiSP pixel rate | how fast the **receiver drains** | the RP1 overclock, via the clock |

### The clock

The overlay re-specifies the RP1 `assigned-clock-rates` array, changing
`RP1_PLL_SYS` and `RP1_CLK_SYS` from 200 MHz to 300 MHz. The clock driver then
picks the nearest rate it can synthesise from the 1 GHz PLL core, which is
**333.33 MHz** — a third of a gigahertz, not the 300 MHz requested. Both the
request and the result are normal; do not treat 333333333 as a fault.

### The pixel-rate ceiling

The PiSP has a CSI2-to-ISP-FE bottleneck that scales with that clock. libcamera
expresses it as `minPixelProcessingTime`, and the IPA uses it to stretch each
mode's minimum line length so the front end can keep up.

Cinemate decides the value and passes it down the stack:

```
settings editor "RP1 overclock" switch
        │  writes
        ▼
/boot/firmware/config.txt        dtoverlay=rp1-overclock
        │  read at launch by
        ▼
cinemate   src/module/rp1_regime.py        → 380 or 580 MPix/s
        │  --max-pixel-rate
        ▼
cinepi-raw core/options.cpp                → setenv()
        │  LIBCAMERA_RPI_MAX_PIXEL_RATE
        ▼
libcamera  src/ipa/rpi/controller/controller.cpp
                                           → minPixelProcessingTime
```

One switch drives the whole chain, so the overlay and the ceiling cannot end up
describing different regimes. The same value is passed to the `--list-cameras`
probe that builds the mode table, so what Cinemate offers you and what it
records with are computed under the same limit.

### Why it is passed rather than detected

libcamera cannot work the rate out for itself. Both obvious ways of asking the
hardware were tried on a CM5 running 6.12.93 and both fail:

- **There is no `rp1` node in `/proc/device-tree`.** Not an empty one — none at
  all, and no `assigned-clock-rates` array anywhere in the tree. A device-tree
  walk finds nothing.
- **The overlay requests 300 MHz and the clock is 333.33 MHz**, so any lookup
  keyed on the requested value misses.

Both failures land silently on the stock rate, which costs frame rate rather
than correctness — safe, but wrong and invisible. Hence an explicit value.

### Why the errors are not symmetric

Setting the ceiling **too low** costs frame rate and nothing else: the IPA pads
the line length further and the sensor runs slower.

Setting it **too high** corrupts. The IPA pads less than the hardware needs,
the CSI2-to-ISP-FE FIFO overruns mid-line, and modes wide enough for this bound
to be what limits the line time return static — with nothing logged, because
the one warning on that path fires when the *sensor* cannot supply enough
blanking, which a too-high rate makes *less* likely to trigger. Narrow modes
are unaffected, since their line rate is sensor-limited and well under either
bound, which is what makes the symptom look like a sensor-mode bug.

So every ambiguous case resolves downward:

| Situation | Ceiling used |
|---|---|
| No RP1 (Pi 4 family) | none passed — libcamera's own default stands |
| Overlay off | 380 MPix/s |
| Overlay on, clock confirms it | 580 MPix/s |
| Overlay on but clock still reads stock — *edited, not yet rebooted* | 380 MPix/s, with a warning naming the reboot |
| Clock unreadable (no root for debugfs) | the switch is believed |

The clock check is a threshold, not an equality test, precisely because the
requested 300 MHz is not the 333.33 MHz that comes out.

### Checking which regime is live

libcamera's own log line is suppressed in normal operation — cinepi-raw calls
`logSetTarget(LoggingTargetNone)` unless `--verbose`, and always for
`--list-cameras` — so read the arguments instead:

```bash
clk=$(sudo -n awk '/^[[:space:]]+clk_sys[[:space:]]/{print $5; exit}' /sys/kernel/debug/clk/clk_summary 2>/dev/null)
pid=$(pgrep -x cinepi-raw | head -1)
rate=$(tr '\0' '\n' < /proc/$pid/cmdline 2>/dev/null | grep -A1 -x -- '--max-pixel-rate' | tail -1)
grep -q '^dtoverlay=rp1-overclock' /boot/firmware/config.txt && ovl=enabled || ovl=stock
printf 'RP1 clk_sys : %s Hz\n' "${clk:-unreadable}"
printf 'config.txt  : rp1-overclock %s\n' "$ovl"
printf 'cinepi-raw  : %s\n' "${rate:-no --max-pixel-rate (libcamera default)}"
```

Read the three lines together: the clock is ground truth, `config.txt` is
intent, and the argument is what the pipeline was actually told. Intent
disagreeing with the clock means you have not rebooted since toggling.

The rest of this page is the manual build.

## 1. Build the RP1 overclock overlay

```bash
sudo apt install -y device-tree-compiler
```

Create `~/rp1-overclock.dts`:

```dts
/dts-v1/;
/plugin/;

/ {
	compatible = "brcm,bcm2712";

	fragment@0 {
		target = <&rp1_clocks>;
		__overlay__ {
			/*
			 * Re-specify the entire assigned-clock-rates array.
			 * Only the items for RP1_PLL_SYS (index #2) and
			 * RP1_CLK_SYS (index #7) have been changed to 300000000.
			 */
			assigned-clock-rates = <
				/* RP1_PLL_SYS_CORE  */ 1000000000
				/* RP1_PLL_AUDIO_CORE*/ 1536000000
				/* RP1_PLL_SYS       */ 300000000
				/* RP1_PLL_SYS_SEC   */ 125000000
				/* RP1_CLK_ETH       */ 125000000
				/* RP1_PLL_AUDIO     */ 61440000
				/* RP1_PLL_AUDIO_SEC */ 153600000
				/* RP1_CLK_SYS       */ 300000000
				/* RP1_PLL_SYS_PRI_PH*/ 100000000
				/* RP1_CLK_SLOW_SYS  */ 50000000
				/* RP1_CLK_SDIO_TIMER*/ 1000000
				/* RP1_CLK_SDIO_ALT_SRC*/ 200000000
				/* RP1_CLK_ETH_TSU   */ 50000000
			>;
		};
	};
};
```

Compile it and install it into the boot overlays directory:

```bash
dtc -@ -I dts -O dtb -o rp1-overclock.dtbo ~/rp1-overclock.dts
sudo cp rp1-overclock.dtbo /boot/firmware/overlays/
```

Then add the overlay to `/boot/firmware/config.txt`:

```
dtoverlay=rp1-overclock
```

## 2. The libcamera side

Nothing to patch. The `cinemate` branch of
[Tiramisioux/libcamera](https://github.com/Tiramisioux/libcamera) reads the
ceiling from `LIBCAMERA_RPI_MAX_PIXEL_RATE` and defaults to the stock
380 MPix/s when it is unset, so one build is correct in both regimes.

Earlier revisions hardcoded `minPixelProcessingTime = 1.0us / 580` here. If you
are looking at an older checkout you will find that edit described as a manual
step — do not reapply it. A build pinned at 580 advertises rates a stock-clock
board cannot drain, and overrunning that bound corrupts wide modes silently
(see [Why the errors are not symmetric](#why-the-errors-are-not-symmetric)).

If you want to override the value by hand for bring-up:

```bash
LIBCAMERA_RPI_MAX_PIXEL_RATE=580 cinepi-raw --verbose ...
```

Cinemate passes `--max-pixel-rate` on every launch, so in normal operation you
never set this yourself.

## 3. Rebuild libcamera

```bash
cd libcamera && \
git config core.fileMode false && \
meson setup build --wipe --buildtype=release \
  -Dpipelines=rpi/vc4,rpi/pisp \
  -Dipas=rpi/vc4,rpi/pisp \
  -Dv4l2=true \
  -Dgstreamer=enabled \
  -Dtest=false \
  -Dlc-compliance=disabled \
  -Dcam=disabled \
  -Dqcam=disabled \
  -Ddocumentation=disabled \
  -Dpycamera=disabled && \
ninja -C build && \
sudo ninja -C build install && \
sudo ldconfig
```

Reboot the Pi.

## 4. Verify

First confirm the clock actually changed. This is the only check that
distinguishes an active overclock from a commented-out overlay:

```bash
sudo grep -E '^[[:space:]]*(pll_sys|clk_sys) ' /sys/kernel/debug/clk/clk_summary
```

The rate is the fifth column:

| Clock | Stock | Overclocked |
|---|---|---|
| `pll_sys` | `200000000` | `333333333` |
| `clk_sys` | `200000000` | `333333333` |

**333333333, not 300000000.** The overlay asks for 300 MHz; the clock driver
rounds to the nearest rate it can make from the 1 GHz PLL core. That is
expected, and measured on a CM5 at 6.12.93.

Then check the advertised modes:

```bash
cinepi-raw --list-cameras
```

With the imx585 and the overclock active you should see:

```text
Available cameras
-----------------
0 : imx585 [3840x2160 12-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [75.00 fps - (0, 0)/3840x2160 crop]
                             3856x2180 [66.85 fps - (0, 0)/3840x2160 crop]
```

```bash
cinepi-raw --list-cameras --hdr sensor
```

```text
Available cameras
-----------------
0 : imx585 [3840x2160 16-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [37.50 fps - (0, 0)/3840x2160 crop]
                             3856x2180 [33.43 fps - (0, 0)/3840x2160 crop]
           'SRGGB16' : 1928x1090 [37.50 fps - (0, 0)/3840x2160 crop]
                       3856x2180 [33.43 fps - (0, 0)/3840x2160 crop]
```

Cinemate probes both lists, so the plain and ClearHDR modes appear together in
the mode table. See [imx585 ClearHDR](clear-hdr.md).


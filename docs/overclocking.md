# Overclocking the Pi

Raise the Raspberry Pi 5 RP1 image-pipeline clock to unlock higher imx585 ClearHDR frame rates. **Pi 5 and CM5 only** — the RP1 southbridge does not exist on the Pi 4 family, so none of this applies there.

!!! warning "Pi 5 / CM5 only"
    Do not apply these steps on a Pi 4 / 400 / CM4. The device-tree overlay
    targets the RP1 (`brcm,bcm2712`) and the libcamera change assumes the PiSP
    (Pi 5) pipeline. Everything the installer does here is gated on that same
    `bcm2712` check, so a Pi 4 install simply skips it.

## What it does

| Change                    | Stock      | Overclocked                               |
| ------------------------- | ---------- | ----------------------------------------- |
| RP1 `PLL_SYS` / `CLK_SYS` | 200 MHz    | **333.33 MHz** (the overlay asks for 300) |
| PiSP pixel-rate ceiling   | 380 MPix/s | 580 MPix/s                                |

The overlay raises the clock. The pixel-rate ceiling tells libcamera how much the pipeline can actually drain, and CineMate sets it to match. Both are needed, and they must agree — see [How it works](#how-it-works).

## What the CineMate install ships

`cinemate-install.sh` does all of this automatically on a Pi 5 / CM5. You do not need the manual steps at the end of this page unless you are building the stack by hand:

| Step                          | Installer function        | Result                                        |
| ----------------------------- | ------------------------- | --------------------------------------------- |
| Compile + install the overlay | `configure_rp1_overclock` | `/boot/firmware/overlays/rp1-overclock.dtbo`  |
| Add the config.txt line       | `configure_boot_config`   | `#dtoverlay=rp1-overclock`, **commented out** |

The overclock therefore ships **installed but off**. Stock clocks stay the default; you opt in. The pixel-rate ceiling needs no install step — CineMate works it out at every launch from whether the overlay is enabled.

### Switching it on and off

Use the **Boot config** pane of the settings editor at `http://cinepi.local:5000/settings-editor`. The **RP1 overclock** toggle comments and uncomments the overlay line for you.

!!! warning "Both directions need a reboot"
    The RP1 clock is set from the device tree at boot, so nothing changes
    until the Pi restarts — switching **on** and switching **off** both
    require it. Restarting CineMate alone does not pick it up. Saving from
    the settings editor reboots for you (**Save & reboot Pi**, roughly 25
    seconds); from a shell you reboot yourself.

The toggle only appears on a `bcm2712` board whose `config.txt` already contains the overlay line. If it is missing, re-run `cinemate-install.sh` to add it. See [Modifying config.txt](config-txt.md) for the file itself.

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

A stock RP1 tops out near 43.8 fps at 4K no matter what the sensor is told to do, which is why the link-frequency menus appear once the overclock is on. Each port has its own — cam0 and cam1 are independent. CineMate writes the parameter only when it differs from the sensor's default:

```
dtoverlay=imx585,cam0,link-frequency=1039500000
```

Per-sensor values live in `resources/sensors.json`. That file is the source of truth — the menu, the validation and the tables below all read from it. See [Sensors](sensors.md) for the full per-sensor tables.

### imx585

| Value                 | Mbps/lane | 4K 12-bit, 4 lanes |
| --------------------- | --------- | ------------------ |
| 297 MHz               | 594       | 20.8 fps           |
| 360 MHz               | 720       | 25.0 fps           |
| 445.5 MHz             | 891       | 30.0 fps           |
| 594 MHz               | 1188      | 41.7 fps           |
| **720 MHz** (default) | 1440      | 50.0 fps           |
| 891 MHz               | 1782      | 60.0 fps           |
| 1039.5 MHz            | 2079      | 75.0 fps           |

Halve for 2-lane, halve again for ClearHDR, double for 2×2 binned. Figures come from [will127534/imx585-v4l2-driver](https://github.com/will127534/imx585-v4l2-driver) and are advisory until measured on this stack. The driver also defines 1188 MHz (2376 Mbps/lane); CineMate does not offer it — the Pi 4 cannot use it
and the Pi 5 drops frames.

### imx283

360 MHz (720 Mbps/lane) and **720 MHz** (1440 Mbps/lane, default). Sony ships exactly two register sequences and the driver rejects anything else.

!!! note "720 MHz is already the ceiling here"
    The only selectable alternative is *slower*. This closes the standing
    question of whether a faster link would lift the 4K modes past their
    44/41 fps: it would, but no faster link exists. More frame rate on the
    imx283 means a lower bit depth, not a faster link.

    Selecting a non-default value needs the `link-frequency` overlay
    parameter, which exists only in `Tiramisioux/imx283-v4l2-driver` `6.12.y`
    at `257c9cf` or later. An older overlay rejects the unknown parameter and
    the camera will not enumerate at all — re-run the installer first.

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

CineMate passes `--max-pixel-rate` on every launch, so in normal operation you
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

Confirm CineMate's own decision, not the clock — on a 6.12.93 kernel
`clk_sys` has been measured at ~333 MHz in *both* regimes, so it can no
longer distinguish an active overclock from a commented-out overlay (see
"Checking which regime is live" above). Check `config.txt` and the actual
`cinepi-raw` launch argument agree instead:

```bash
grep -q '^dtoverlay=rp1-overclock' /boot/firmware/config.txt && echo enabled || echo stock
pid=$(pgrep -x cinepi-raw | head -1)
tr '\0' '\n' < /proc/$pid/cmdline 2>/dev/null | grep -A1 -x -- '--max-pixel-rate'
```

Stock is `380`, overclocked is `580`. If you want to read the clock anyway as
a secondary sanity check:

```bash
sudo grep -E '^[[:space:]]*(pll_sys|clk_sys) ' /sys/kernel/debug/clk/clk_summary
```

The rate is the fifth column. **333333333, not 300000000** — the overlay asks
for 300 MHz; the clock driver rounds to the nearest rate it can make from the
1 GHz PLL core. That figure alone does not tell you which regime is active on
this kernel; it was only ever a reliable discriminator on an earlier
6.12.93 session that measured stock at `200000000`.

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

CineMate probes both lists, so the plain and ClearHDR modes appear together in
the mode table. See [imx585 ClearHDR](clear-hdr.md).


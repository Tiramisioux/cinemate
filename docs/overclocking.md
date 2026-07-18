# Overclocking the Pi

Raise the Raspberry Pi 5 RP1 image-pipeline clock to unlock higher imx585
ClearHDR frame rates. **Pi 5 only** — the RP1 southbridge does not exist on the
Pi 4 family, so none of this applies there.

Instructions courtesy of **Will Whang**, with thanks. See his work at
[github.com/will127534](https://github.com/will127534).

!!! warning "Pi 5 only"
    Do not apply these steps on a Pi 4 / 400 / CM4. The device-tree overlay
    targets the RP1 (`brcm,bcm2712`) and the libcamera change assumes the PiSP
    (Pi 5) pipeline.

## What it does

| Change | Default | Overclocked |
|---|---|---|
| RP1 `PLL_SYS` / `CLK_SYS` | 200 MHz | 300 MHz |
| libcamera `minPixelProcessingTime` (pisp) | `1.0us / 380` | `1.0us / 580` |

The RP1 overlay raises the clock; the libcamera change lifts the pixel-rate cap
so the pipeline can actually advertise the faster modes. Both are needed.

## What the Cinemate image ships

The prebuilt Cinemate image is already built overclock-ready:

- libcamera is compiled with `minPixelProcessingTime = 1.0us / 580`.
- The `rp1-overclock` overlay is installed but **commented out** in
  `/boot/firmware/config.txt`.

To enable the overclock, uncomment the overlay and reboot:

```bash
sudo sed -i 's/^#\s*dtoverlay=rp1-overclock/dtoverlay=rp1-overclock/' /boot/firmware/config.txt
sudo reboot
```

To go back to stock, re-comment the line and reboot. The rest of this page is
for a manual build.

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

## 2. Patch libcamera

In the libcamera source, edit `src/ipa/rpi/controller/controller.cpp`. Under the
`pisp` section, change:

```cpp
.minPixelProcessingTime = 1.0us / 380,
```

to:

```cpp
.minPixelProcessingTime = 1.0us / 580,
```

## 3. Rebuild libcamera

Leave the Cinemate virtualenv first so meson uses the system Python:

```bash
deactivate
```

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


## RP1 overclock (Pi 5): higher sensor frame rates

The RP1 I/O chip's clock limits CSI-2 throughput. Raising RP1_PLL_SYS and
RP1_CLK_SYS from 200 to 300 MHz lifts the imx585 to 75 fps at 2K / 66.85 fps
at 4K (SDR), and 37.5 / 33.43 fps in ClearHDR. Method by **Will Whang** —
credit and thanks: <https://github.com/will127534>.

Pi 5 / CM5 only. The Cinemate image ships the overlay compiled but **commented
out** in `/boot/firmware/config.txt`; uncomment `#dtoverlay=rp1-overclock` to
enable, then reboot.

Manual setup: save the overlay source below as `~/rp1-overclock.dts`, then:

```bash
sudo apt install device-tree-compiler
dtc -@ -I dts -O dtb -o rp1-overclock.dtbo ~/rp1-overclock.dts
sudo cp rp1-overclock.dtbo /boot/firmware/overlays/
echo '#dtoverlay=rp1-overclock' | sudo tee -a /boot/firmware/config.txt   # uncomment to enable
```

```dts
/dts-v1/;
/plugin/;

/ {
	compatible = "brcm,bcm2712";

	fragment@0 {
		target = <&rp1_clocks>;
		__overlay__ {
			/* Entire assigned-clock-rates array re-specified; only
			 * RP1_PLL_SYS (#2) and RP1_CLK_SYS (#7) changed to 300 MHz. */
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

libcamera must be told about the faster ISP: in
`~/libcamera/src/ipa/rpi/controller/controller.cpp`, under the "pisp" section,
change `.minPixelProcessingTime = 1.0us / 380` to `1.0us / 580`, rebuild
libcamera (meson/ninja install as in the install guide), and reboot.

Verify with `cinepi-raw --list-cameras` (expect 75 / 66.85 fps) and
`cinepi-raw --list-cameras --hdr sensor` (expect 37.5 / 33.43 fps, with the
SRGGB16 modes listed).

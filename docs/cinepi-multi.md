# How Cinemate launches CinePi-raw

`src/module/cinepi_multi.py` starts one `cinepi-raw` process per detected camera. It combines camera discovery from `sensor_detect.py`, Redis state, and user settings from `settings.json` to build the command line for each process.

## Detecting cameras

At startup, `CinePiManager.start_all()` runs `cinepi-raw --list-cameras` and retries until a camera list is returned or the discovery timeout expires. Each detected camera is classified onto `cam0` or `cam1`, then published to Redis as the `cameras` JSON blob.

!!! tip

    You can narrow down the list of selectable modes via the `resolutions` section in `settings.json`. Only modes whose width falls into one of your chosen *K* categories and whose bit depth matches will be shown. Custom driver modes not reported by `cinepi-raw` can also be added there.

Before any process is launched, Cinemate also seeds the preview `zoom` key from `preview.default_zoom` if Redis does not already contain a zoom value.

## Building the `cinepi-raw` command

For each detected camera, the manager creates a `CinePiProcess`. `_build_args()` assembles flags for:

- the selected sensor mode, width, height, and bit depth
- the raw packing suffix for the selected Pi generation
- per-camera geometry from `geometry.cam0`, `geometry.cam1`, and so on
- per-camera HDMI output mapping from the `output` section
- the low-resolution preview size used by CinePi-raw

The preview size is based on `hdmi_display.width` and `hdmi_display.height`, but if a framebuffer is already active, Cinemate prefers the real framebuffer size instead of forcing the configured canvas. That avoids drawing a clipped `1920x1080` preview into a smaller active mode.

Here is a simplified example of the resulting command:

```bash
cinepi-raw --mode 2028:1080:12:U \
           --width 2028 --height 1080 \
           --lores-width 1280 --lores-height 720 \
           --hdmi-port 0 --rotation 0 --hflip 0 --vflip 0 \
           --post-process-file /home/pi/post-processing0.json \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json
```

On Raspberry Pi 4 / Pi 400 / CM4, Cinemate switches IMX296 and IMX477 launches to packed raw mode (`P`), for example `1456:1088:10:P` for IMX296. On Raspberry Pi 5 / CM5 it leaves those sensors on unpacked raw mode (`U`). Pi 4-family launches also skip the PiSP tuning-file argument and use the VC4 camera stack.

## Multi-camera startup details

In multi-camera mode, the first process is launched with `--sync server` and the rest use `--sync client`. Only the primary process gets the on-screen preview rectangle; secondary cameras run with `--nopreview`.

After launch, Cinemate waits for all expected `cinepi_ready_*` Redis keys before it considers the camera stack ready. This is important because it makes sure the first REC edge reaches every camera instead of only the process that happened to finish booting first.

Once all cameras are up, Cinemate republishes `zoom` if the startup zoom is not `1.0` so the running CinePi-raw processes apply the initial crop immediately.

## Log forwarding and last-frame tracking

Each `CinePiProcess` forwards log output and watches for `DNG written:` lines from the encoder. Those log lines are used to keep `last_dng_cam0` and `last_dng_cam1` up to date in Redis.

On shutdown, the manager stops all child processes and removes any leftover `cinepi_ready_*` keys from Redis so the next boot starts cleanly.


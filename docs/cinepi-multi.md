# How Cinemate launches cinepi-raw

`cinemate/src/module/cinepi_multi.py`  starts one `cinepi-raw` process per connected camera. It takes user settings from `sensor_detect.py` and `settings.json` to influence the command-line flags passed to `cinepi-raw`.

Here it how it works:

## Detecting Cameras

When CineMate starts, `CinePiManager` runs `cinepi-raw --list-cameras`. Each line of output describes a connected sensor. The manager parses this output and stores basic information about every camera:

- **index** – numeric index passed to `--camera`
- **model** – sensor model name (e.g. `imx477`)
- **mono** – whether the camera is monochrome

This information is kept in the `CameraInfo` class and written to Redis under the `cam_info` keys so that other modules know which sensors are present.

## Loading Resolution Data

`cinepi_multi.py` relies on `sensor_detect.py` to look up valid resolutions and frame rates for each sensor. From version 3.1 the list of modes is parsed automatically from the output of `cinepi-raw --list-cameras`. Packing information and optional FPS correction factors are stored per sensor in `sensor_detect.py`.

You can narrow down the list of selectable modes via the `resolutions` section in `settings.json`. Only modes whose width falls into one of your chosen *K* categories and whose bit depth matches will be shown. Custom modes not reported by `cinepi-raw` can also be added here.

## Building the `cinepi-raw` Command

For each detected camera the manager creates a `CinePiProcess`. The `_build_args()` method constructs a list of command-line flags for `cinepi-raw`:

1. **Resolution flags** – `--mode`, `--width`, `--height` are taken from `sensor_detect`.
2. **Preview size** – low‑resolution dimensions are calculated so that the preview fits inside the HDMI framebuffer. The values are stored in Redis as `lores_width` and `lores_height`.
3. **Geometry** – the `geometry` section in `settings.json` allows you to rotate or flip each camera. These settings translate to `--rotation`, `--hflip` and `--vflip` flags.
4. **Output mapping** – the `output` section chooses which HDMI connector each camera uses. The primary camera shows a preview window unless `--nopreview` is specified.
5. **Synchronization** – if more than one camera is present, the first one is started with `--sync server` and the rest with `--sync client` so that frame capture is aligned.

Here is a simplified example of the resulting command:

```bash
cinepi-raw --camera 0 --mode 2028:1080:12:U \
           --width 2028 --height 1080 \
           --lores-width 1280 --lores-height 720 \
           --hdmi-port 0 --rotation 0 --hflip 0 --vflip 0 \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json
```

Secondary cameras would receive `--nopreview` and a different `--hdmi-port` based on your settings.

>`cinepi_multi.py` lives in `src/module/`. If you want to change how arguments are built, look inside the `_build_args()` method. The rest of the file deals with process management, log forwarding and readiness checks.

## Waiting for Cameras to Become Ready

Each `cinepi-raw` instance prints `Encoder configured` when it has finished initialising. `cinepi_multi` watches the output and sets a Redis key like `cinepi_ready_cam0`. The manager waits until every launched camera reports ready before CineMate proceeds. This ensures that the very first REC command is seen by all sensors simultaneously.

## Customising Behaviour

- **`sensor_detect.py`** – adjust the packing or FPS correction factor dictionaries if needed for new sensors.
- **`settings.json`** – update the `geometry` and `output` sections for per‑camera rotation, flipping and HDMI mapping. These settings are read at startup and directly influence the arguments passed to `cinepi-raw`.


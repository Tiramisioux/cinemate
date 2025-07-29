# How Cinemate launches cinepi-raw

`cinemate/src/module/cinepi_multi.py`  starts one `cinepi-raw` process per connected camera. It takes camera information `cinemate/src/module/sensor_detect.py` and user settings from `cinemate/src/module/settings.json` to build the command and command-line flags passed to `cinepi-raw`.


## Detecting Cameras

When CineMate starts, `cinemate/src/module/cinepi_multi.py/CinePiManager` runs the cli command `cinepi-raw --list-cameras`. The manager parses this output and stores resolution modes for each attached camera.

!!! tip

     You can narrow down the list of selectable modes via the `resolutions` section in `settings.json`. Only modes whose width falls into one of your chosen *K* categories and whose bit depth matches will be shown. Custom driver modes not reported by `cinepi-raw` can also be added here.
    
## Building the `cinepi-raw` Command

For each detected camera the manager creates a `CinePiProcess`. The `_build_args()` method constructs a list of command-line flags for `cinepi-raw`.

Here is an example of the resulting command:

```bash
cinepi-raw --camera 0 --mode 2028:1080:12:U \
           --width 2028 --height 1080 \
           --lores-width 1280 --lores-height 720 \
           --hdmi-port 0 --rotation 0 --hflip 0 --vflip 0 \
           --tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/imx477.json
```

!!! note

     If you want to change how arguments are built, look inside the `_build_args()` method. The rest of the file deals with process management, log forwarding and readiness checks.




# Page chrome

The six tabs across the top of the settings editor, and the sidebar groups down the left.
The heading line is the label; the paragraph under it is the smaller text beneath it.

## Tabs

### config.txt
<!-- key: tab.config -->

boot & sensors

### i2c
<!-- key: tab.i2c -->

i2c hardware

### settings.jsonc
<!-- key: tab.settings -->

cameras, audio, controls

### Live view
<!-- key: tab.live -->

test camera & controls

### Playback
<!-- key: tab.playback -->

review takes

### RAW files
<!-- key: tab.raw -->

browse & download

## Sidebar groups

### Boot config
<!-- key: rail.boot-config -->

Sensor overlays, hardware buses and the RP1 overclock — everything Cinemate writes into `config.txt`. Every change here needs a reboot.

### Look & feel
<!-- key: rail.look-and-feel -->

_(no blurb — this group is just a heading over links)_

#### Welcome screen
<!-- key: raillink.welcome -->

#### Wi‑Fi hotspot
<!-- key: raillink.wifi -->

### Cameras
<!-- key: rail.cameras -->

_(no blurb — this group is just a heading over links)_

#### Camera 0
<!-- key: raillink.cam0 -->

#### Camera 1
<!-- key: raillink.cam1 -->

### Timing
<!-- key: rail.timing -->

_(no blurb — this group is just a heading over links)_

#### Timing & sync
<!-- key: raillink.sync -->

### Exposure & steps
<!-- key: rail.exposure-and-steps -->

_(no blurb — this group is just a heading over links)_

#### Value steps
<!-- key: raillink.steps -->

#### Resolution & sensor
<!-- key: raillink.resolution -->

#### Per-mode fps ceilings
<!-- key: raillink.fpsceilings -->

### Recording
<!-- key: rail.recording -->

_(no blurb — this group is just a heading over links)_

#### Audio
<!-- key: raillink.audio -->

#### HDMI & preview
<!-- key: raillink.hdmi -->

### Physical controls
<!-- key: rail.physical-controls -->

_(no blurb — this group is just a heading over links)_

#### Buttons & switches
<!-- key: raillink.controls -->

#### Grove HAT potentiometers
<!-- key: raillink.pots -->

#### Quad rotary encoder
<!-- key: raillink.quadrotary -->

#### Rec tally & GPIO out
<!-- key: raillink.gpio -->

#### OLED status display
<!-- key: raillink.oled -->

### System
<!-- key: rail.system -->

_(no blurb — this group is just a heading over links)_

#### Restart Cinemate
<!-- key: raillink.system -->

### i2c hardware
<!-- key: rail.i2c-hardware -->

What is attached to the camera's I²C bus, probed each time you open this tab. Everything here is optional — the camera shoots without any of it.

### RAW files
<!-- key: rail.raw-files -->

Everything on the active storage device — browse, sort and pull takes off over Wi‑Fi.

### Playback
<!-- key: rail.playback -->

Review takes off the card at the conform frame rate.

### Live view
<!-- key: rail.live-view -->

The shooting screen — image, ISO/shutter/fps/WB, and everything `simple_gui.py` already draws on the HDMI overlay, mirrored to the browser. It is the camera's own page on port `5000`, embedded here. For the picture on its own with nothing drawn over it, use port `8000` instead — `8001` for a second sensor.

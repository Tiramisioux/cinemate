# Pinefeat adapter

The [Pinefeat CEF168](https://www.pinefeat.co.uk) is an adapter board for **Canon EF and EF-S lenses**. It sits between the camera module and the Pi on the camera cable. It gives the Pi electronic control of the lens iris and focus motor over I²C.

CineMate talks to the board itself. **Basic use needs nothing installed.**

## What CineMate does with it

| Feature | What it does | Needs |
|---|---|---|
| Iris | Sets the aperture in third stops. Step it with buttons, dials or a pot. | Nothing installed |
| Focus | Moves the focus motor. Step it with buttons or dials. | Nothing installed |
| Calibration | Learns the lens's focus range. One button, one command, or one gesture on the lens. | Nothing installed |
| Lens database | Remembers each lens: name, aperture range, last iris, focus calibration. | Nothing installed |

## What it does not do

| Not available | Why |
|---|---|
| Autofocus | Paused. Focus is manual. |
| Zoom | Canon EF lenses have no power zoom. CineMate shows no focal length. |
| Reading the aperture range | The board reports it only on its serial port, not over I²C. You enter it once per lens: [Lenses](lenses.md#aperture-range). |
| Reading the real aperture | The lens cannot report it. CineMate shows the f-number it last commanded. |
| Every lens | Some lenses only partly work. See [Compatibility](compatibility.md). |

## Two ways CineMate reaches the board

| Way | When | What changes |
|---|---|---|
| **Raw I²C** | Always available. The board answers at address `0x0d` on the camera's own I²C bus. | Nothing to install. Iris, focus, calibration, lens database. |
| **Kernel driver** | Optional. After the [driver install](install.md#kernel-driver-level-optional). The driver owns the board and CineMate goes through it. | Same features. The board also shows up as a V4L2 lens device for other tools. |

The settings editor shows which way is in use. CineMate goes through the driver whenever the lens device exists.

## Platforms

All four CineMate platforms work. CineMate finds the adapter's I²C bus itself. The bus number differs between boards and carriers, so there is nothing to configure.

| Board | Basic use | Kernel driver (optional) | Overlay line |
|---|---|---|---|
| Raspberry Pi 5 | yes | yes | `dtoverlay=cef168,cam0,<sensor>` or `cam1` |
| Compute Module 5 | yes | yes | `dtoverlay=cef168,cam0,<sensor>` or `cam1` |
| Compute Module 4 | yes | yes | `dtoverlay=cef168,cam0,<sensor>` or `cam1` |
| Raspberry Pi 4B | yes | yes | `dtoverlay=cef168,<sensor>` (one port, no `cam0`/`cam1`) |

The port in the overlay line must match the port in the sensor's own `dtoverlay` line. See [Raspberry Pi models](../raspberry-pi-models.md) for the per-board differences.

## Where to go next

| Page | What is in it |
|---|---|
| [Installation](install.md) | Basic level, optional kernel driver (scripted and by hand), undoing Pinefeat's own installer |
| [Panes and controls](panes.md) | How the HDMI GUI, web GUI, settings editor, CLI and physical controls show and use the adapter |
| [Lenses and calibration](lenses.md) | The lens database, calibration, aperture range, per-lens capabilities |
| [Compatibility](compatibility.md) | Tested lenses, troubleshooting, how to report a lens |

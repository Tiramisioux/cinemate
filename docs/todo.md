## Todo

```todo
- simple_gui.py adaptive layout for non 1920x1080 screens
- 16 bit modes for imx585
- support for imx294
- overclocking of ISP
- optional auto-exposure
- hardware sync of sensor frame capture, perhaps via a pico
- rendering mode, for creating proxy files in camera (using https://github.com/mrjulesfletcher/dng_to_video)
- automatic detection of attached sensor and dynamic dtoverlay
```


<!-- ::schemdraw:: alt="Raspberry Pi 40-pin header (colour-coded)"
    += elm.Dot(color='#ff9800', radius=0.09).at((0,  0.00)).label('3V3',  'left')
    += elm.Dot(color='#f44336', radius=0.09).at((1,  0.00)).label('5V',   'right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -0.25)).label('GPIO 2','left')
    += elm.Dot(color='#f44336', radius=0.09).at((1, -0.25)).label('5V',   'right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -0.50)).label('GPIO 3','left')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((1, -0.50)).label('GND',  'right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -0.75)).label('GPIO 4','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -0.75)).label('GPIO 14','right')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((0, -1.00)).label('GND',  'left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -1.00)).label('GPIO 15','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -1.25)).label('GPIO 17','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -1.25)).label('GPIO 18','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -1.50)).label('GPIO 27','left')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((1, -1.50)).label('GND', 'right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -1.75)).label('GPIO 22','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -1.75)).label('GPIO 23','right')
    += elm.Dot(color='#ff9800', radius=0.09).at((0, -2.00)).label('3V3','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -2.00)).label('GPIO 24','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -2.25)).label('GPIO 10','left')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((1, -2.25)).label('GND','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -2.50)).label('GPIO 9','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -2.50)).label('GPIO 25','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -2.75)).label('GPIO 11','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -2.75)).label('GPIO 8','right')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((0, -3.00)).label('GND','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -3.00)).label('GPIO 7','right')
    += elm.Dot(color='#2196f3', radius=0.09).at((0, -3.25)).label('ID_SD','left')
    += elm.Dot(color='#2196f3', radius=0.09).at((1, -3.25)).label('ID_SC','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -3.50)).label('GPIO 5','left')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((1, -3.50)).label('GND','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -3.75)).label('GPIO 6','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -3.75)).label('GPIO 12','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -4.00)).label('GPIO 13','left')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((1, -4.00)).label('GND','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -4.25)).label('GPIO 19','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -4.25)).label('GPIO 16','right')
    += elm.Dot(color='#4caf50', radius=0.09).at((0, -4.50)).label('GPIO 26','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -4.50)).label('GPIO 20','right')
    += elm.Dot(color='#9e9e9e', radius=0.09).at((0, -4.75)).label('GND','left')
    += elm.Dot(color='#4caf50', radius=0.09).at((1, -4.75)).label('GPIO 21','right')


    += elm.Resistor().right().at((1, -4.75)).label('220 Ω')
    += elm.LED().right().label('LED')
    += elm.Line().down().length(0.35)              # drop below the LED
    += elm.Line().left().tox(0).dot()              # into the GND dot (pin 39)
::end-schemdraw::

 -->

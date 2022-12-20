#!/bin/sh
# install.sh will install the necessary packages to get the CineMate-HAT working. Will also add a second I2C channel on channel 6.


## Enable I2C, SPI and second I2C channel on GPIO pins 22 (SDA channel 6) and 23 (SCL channel6) and change monitor resolution to 1920x1080

CONFIG="/boot/config.txt"

# If a line containing "dtparam=i2c_arm=off" exists
if grep -Fq "dtparam=i2c_arm=off" $CONFIG
then
	# Replace the line
	echo "Enabling i2C"
	sed -i "s/dtparam=i2c_arm=off/dtparam=i2c_arm=on/g" $CONFIG
else
	# Create the definition
	echo "I2C not defined. Creating definition"
	echo "dtparam=i2c_arm=on" >> $CONFIG
fi

# Enable I2C channel 6
echo "Adding second I2C channel"
echo "dtoverlay=i2c-gpio,bus=6,i2c_gpio_delay_us=1,i2c_gpio_sda=22,i2c_gpio_scl=23" >> $CONFIG

# If a line containing "#dtparam=spi=on" exists
if grep -Fq "#dtparam=spi=on" $CONFIG
then
	# Replace the line
	echo "Enabling SPI"
	sed -i "s/#dtparam=spi=on/dtparam=spi=on/g" $CONFIG
else
	# Create the definition
	echo "SPI not defined. Creating definition"
	echo "dtparam=spi=on" >> $CONFIG
fi

# Install packages
cd ~
sudo apt-get update -y
sudo apt upgrade -y

#I2C
sudo pip3 install smbus2
sudo apt-get install -y python-smbus
sudo apt install -y i2c-tools python3-smbus

# Install ADC
sudo apt-get install build-essential python-dev python-smbus git -y
git clone https://github.com/adafruit/Adafruit_Python_ADS1x15.git
cd ~
cd Adafruit_Python_ADS1x15
sudo python3 setup.py install

#OLED
sudo -H pip3 install --upgrade luma.oled
sudo apt-get install python3 python3-pip python3-pil libjpeg-dev zlib1g-dev libfreetype6-dev liblcms2-dev libopenjp2-7 libtiff5 -y
sudo -H pip3 install luma.oled
sudo usermod -a -G spi,gpio,i2c pi


#Add RTC
MODULES="/etc/modules"
echo "i2c-bcm2708" >> $MODULES
echo "i2c-dev" >> $MODULES
echo "rtc-ds1307" >> $MODULES

sed -i '/exit 0/i \echo ds1307 0x68 > /sys/class/i2c-adapter/i2c-6/new_device &\hwclock -s &' /etc/rc.local

#Clone the Cinemate repository
cd ~
git clone https://github.com/Tiramisioux/cinemate.git

# Change shutter speed display to shutter angle display

# Rename the file /camera/mmal_render_ui/render.c to render_original.c
mv /camera/mmal_render_ui/render.c /camera/mmal_render_ui/render_original.c

# Copy the file /cinemate/render.c to the folder /camera/mmal_render_ui
cp /cinemate/render.c /camera/mmal_render_ui

# Change to the directory containing the file
cd /camera/mmal_render_ui

# Recompile the file using the command make -j 4
make -j 4

# Change /camera/cameracore3.py

# Rename the file
mv /camera/cameracore3.py /camera/cameracore3_original.py

# Copy the file
cp /cinemate/cameracore3.py /camera/cameracore3.py


echo "Install complete, rebooting."
reboot

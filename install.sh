#!/bin/sh
# install.sh will install the necessary packages to get the CineMate-HAT working. Will also add a second I2C channel on channel 6.

# git clone https://github.com/Tiramisioux/cinemate.git
# cd cinemate
# chmod +x install.sh
# sudo ./install.sh

## Enable I2C, SPI and second I2C channel on GPIO22 (SDA) and GPIO23 (SCL)

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
echo "Adding I2C-6 (SDA on GPIO22, SCL on GPIO23"
echo "dtoverlay=i2c6" >> $CONFIG

#Disable Bluetooth
echo "Disabling Bluetooth"
echo "dtoverlay=pi3-disable-bt" >> $CONFIG

#Enable safe shutdown on GPIO pin 3
echo "Enabling safe shutdown on GPIO 03"
echo "dtoverlay=gpio-shutdown" >> $CONFIG


# Install packages
echo "Installing packages"
cd ~
sudo apt-get update -y
sudo apt upgrade -y

#I2C
echo "I2C"
sudo pip3 install smbus2
sudo apt-get install -y python-smbus
sudo apt install -y i2c-tools python3-smbus

# Install ADC
echo "ADC"
sudo apt-get install build-essential python-dev python-smbus git -y
git clone https://github.com/adafruit/Adafruit_Python_ADS1x15.git
cd ~
cd Adafruit_Python_ADS1x15
sudo python3 setup.py install

#OLED
echo "OLED"
sudo -H pip3 install --upgrade luma.oled
sudo apt-get install python3 python3-pip python3-pil libjpeg-dev zlib1g-dev libfreetype6-dev liblcms2-dev libopenjp2-7 libtiff5 -y
sudo -H pip3 install luma.oled
sudo usermod -a -G spi,gpio,i2c pi

#Add RTC
echo "Installing RTC module"
MODULES="/etc/modules"
echo "i2c-bcm2708" >> $MODULES
echo "i2c-dev" >> $MODULES
echo "rtc-ds1307" >> $MODULES

sed -i '/exit 0/i \echo ds1307 0x68 > /sys/class/i2c-adapter/i2c-6/new_device &\hwclock -s &' /etc/rc.local

# Change shutter speed display to shutter angle display
echo "Changing shutter speed display to shutter angle display"
cd ~
# Rename the file /camera/mmal_render_ui/render.c to render_original.c
mv mmal_render_ui/render.c mmal_render_ui/render_original.c

# Copy the file /cinemate/render.c to the folder /camera/mmal_render_ui
cp cinemate/render.c mmal_render_ui/render.c

# Change to the directory containing the file
cd mmal_render_ui

# Recompile the file using the command make -j 4
make -j 4

# Change /camera/cameracore3.py
echo "Replacing /camera/cameracore3.py to start cinemate scripts. Original file is saved as camera/cameracore3_original.py"
cd ~ 
# Rename the file
mv camera/cameracore3.py camera/cameracore3_original.py

# Copy the file
cp cinemate/cameracore3.py camera/cameracore3.py

# Install Pi-shrink, for backing up SD card
echo "Installing Pi-shrink, for backing up SD card"
cd ~
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
sudo chmod +x pishrink.sh
sudo mv pishrink.sh /usr/local/bin

#Reboot
echo "Install complete, rebooting."
reboot
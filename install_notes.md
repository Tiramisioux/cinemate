//Grove Base hat

sudo apt-get install build-essential python3-dev python3-pip python3-smbus python3-serial git
sudo pip3 install -U setuptools wheel
sudo pip3 install -U grove.py

git clone https://github.com/Seeed-Studio/grove.py.git
cd grove.py
sudo python3 setup.py install


// Modifications to cinepi-raw


// Install RTC unit


#!/bin/bash

# Cinemate & cinepi-raw "one click" installer
# Follows docs/installation-steps.md.
# The script sets up a systemd service so it resumes after reboots.

set -e

STATE_FILE="/opt/cinemate-installer/state"
INSTALL_DIR="/opt/cinemate-installer"
SERVICE_FILE="/etc/systemd/system/cinemate-installer.service"

# ---------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------
save_state() {
    echo "$1" > "$STATE_FILE"
}

load_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo 0
    fi
}

ensure_service() {
    mkdir -p "$INSTALL_DIR"
    cp "$0" "$INSTALL_DIR/install.sh"
    cat > "$SERVICE_FILE" <<'SERVICE'
[Unit]
Description=Cinemate Installer
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/cinemate-installer/install.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
SERVICE
    systemctl daemon-reload
    systemctl enable cinemate-installer.service
}

# ---------------------------------------------------------------
# Installation step functions
# ---------------------------------------------------------------

step_install_base_packages() {
    # Basic utilities for libcamera and building
    apt update
    apt install -y python3-pip git python3-jinja2
}

step_install_libcamera() {
    # Clone and build libcamera 1.7.0
    su - pi -c "git clone https://github.com/raspberrypi/libcamera"
    su - pi -c "find ~/libcamera -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} \;"
    su - pi -c "cd ~/libcamera && meson setup build --buildtype=release \
      -Dpipelines=rpi/vc4,rpi/pisp \
      -Dipas=rpi/vc4,rpi/pisp \
      -Dv4l2=true \
      -Dgstreamer=enabled \
      -Dtest=false \
      -Dlc-compliance=disabled \
      -Dcam=disabled \
      -Dqcam=disabled \
      -Ddocumentation=disabled \
      -Dpycamera=enabled"
    su - pi -c "cd ~/libcamera && ninja -C build install"
}

step_libcamera_utils_permissions() {
    # Ensure utilities have execute permission and reinstall
    su - pi -c "cd ~/libcamera/utils && chmod +x *.py *.sh && chmod +x ~/libcamera/src/ipa/ipa-sign.sh && cd ~/libcamera && ninja -C build install"
}

step_fix_libtiff() {
    apt-get install --reinstall -y libtiff5-dev
    ln -sf $(find /usr/lib -name 'libtiff.so' | head -n 1) /usr/lib/aarch64-linux-gnu/libtiff.so.5
    export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
    ldconfig
}

step_extra_dependencies() {
    apt install -y python3-pip git python3-jinja2 libboost-dev libgnutls28-dev openssl \
        pybind11-dev qtbase5-dev libqt5core5a meson cmake python3-yaml python3-ply \
        libglib2.0-dev libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libavdevice59
}

step_install_nvm() {
    su - pi -c "wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash"
    su - pi -c "source ~/.bashrc && nvm install --lts"
}

step_install_cpp_mjpeg_streamer() {
    apt install -y libspdlog-dev libjsoncpp-dev
    su - pi -c "cd ~ && git clone https://github.com/Tiramisioux/cpp-mjpeg-streamer.git --branch cinemate"
    su - pi -c "cd ~/cpp-mjpeg-streamer && mkdir build && cd build && cmake .. && make && make install-here"
}

step_cinepi_raw_deps() {
    apt install -y cmake libepoxy-dev libavdevice-dev build-essential libboost-program-options-dev \
        libdrm-dev libexif-dev libcamera-dev libjpeg-dev libtiff5-dev libpng-dev redis-server \
        libhiredis-dev libasound2-dev libjsoncpp-dev meson ninja-build libavcodec-dev libavdevice-dev \
        libavformat-dev libswresample-dev
    apt-get install -y libjsoncpp-dev
    su - pi -c "cd ~ && git clone https://github.com/sewenew/redis-plus-plus.git && cd redis-plus-plus && mkdir build && cd build && cmake .. && make && make install"
}

step_build_cinepi_raw() {
    su - pi -c "git clone https://github.com/Tiramisioux/cinepi-raw.git --branch rpicam-apps_1.7_custom_encoder"
    su - pi -c "cd ~/cinepi-raw && rm -rf build || true && export PKG_CONFIG_PATH=/home/pi/cpp-mjpeg-streamer/build:\$PKG_CONFIG_PATH && meson setup build && ninja -C build && meson install -C build"
}

step_python_venv() {
    apt update
    apt install -y python3-venv
    su - pi -c "python3 -m venv /home/pi/.cinemate-env"
    echo "source /home/pi/.cinemate-env/bin/activate" >> /home/pi/.bashrc
    su - pi -c "source /home/pi/.cinemate-env/bin/activate"
}

step_grant_sudo_i2c() {
    echo "pi ALL=(ALL) NOPASSWD: /home/pi/.cinemate-env/bin/*" > /etc/sudoers.d/cinemate-env
    chown -R pi:pi /home/pi/.cinemate-env
    chown -R pi:pi /media && chmod 755 /media
    usermod -aG i2c pi
    modprobe i2c-dev && echo i2c-dev >> /etc/modules
    echo "pi ALL=(ALL) NOPASSWD: /home/pi/run_cinemate.sh" > /etc/sudoers.d/pi_cinemate
}

step_cinemate_deps() {
    su - pi -c "source /home/pi/.cinemate-env/bin/activate && python3 -m pip install --upgrade pip setuptools wheel"
    apt-get install -y i2c-tools portaudio19-dev build-essential python3-dev python3-pip python3-smbus python3-serial git
    su - pi -c "source /home/pi/.cinemate-env/bin/activate && pip3 install adafruit-circuitpython-ssd1306 watchdog psutil Pillow redis keyboard pyudev sounddevice smbus2 gpiozero RPI.GPIO evdev termcolor pyserial inotify_simple numpy rpi_hardware_pwm"
    su - pi -c "source /home/pi/.cinemate-env/bin/activate && pip3 uninstall -y Pillow && pip3 install Pillow"
    su - pi -c "source /home/pi/.cinemate-env/bin/activate && pip3 install sugarpie flask_socketio board adafruit-blinka adafruit-circuitpython-seesaw luma.oled grove.py pigpio-encoder gpiod"
    apt install -y python3-systemd e2fsprogs ntfs-3g exfatprogs console-terminus
}

step_replace_rpi_gpio() {
    apt install -y swig python3-dev build-essential git
    su - pi -c "git clone https://github.com/joan2937/lg && cd lg && make && sudo make install && cd .. && pip install lgpio"
}

step_clone_cinemate() {
    su - pi -c "git clone https://github.com/Tiramisioux/cinemate.git /home/pi/cinemate"
}

step_allow_main_sudo() {
    echo 'pi ALL=(ALL) NOPASSWD: /home/pi/cinemate/src/main.py' >> /etc/sudoers.d/pi_cinemate
    echo 'pi ALL=(ALL) NOPASSWD: /bin/mount, /bin/umount, /usr/bin/ntfs-3g' >> /etc/sudoers.d/pi_cinemate
    echo 'pi ALL=(ALL) NOPASSWD: /home/pi/cinemate/src/logs/system.log' >> /etc/sudoers.d/pi_cinemate
    echo 'pi ALL=(ALL) NOPASSWD: /sbin/mount.ext4' >> /etc/sudoers.d/pi_cinemate
}

step_enable_network_manager() {
    systemctl enable NetworkManager --now
}

step_rotate_logs() {
    cat > /etc/logrotate.d/general_logs <<'EOP'
/var/log/*.log {
   size 100M
   rotate 5
   compress
   missingok
   notifempty
}
EOP
}

step_seed_redis() {
    su - pi -c "redis-cli <<'EOF'
SET anamorphic_factor 1.0
PUBLISH cp_controls anamorphic_factor
SET bit_depth 12
PUBLISH cp_controls bit_depth
EOF"
}

step_alias_bashrc() {
    echo "alias Cinemate='python3 /home/pi/Cinemate/src/main.py'" >> /home/pi/.bashrc
}

step_make_install() {
    su - pi -c "cd /home/pi/cinemate && make install"
}

step_install_services() {
    su - pi -c "cd /home/pi/cinemate/services && make install && make enable"
}

step_cleanup() {
    systemctl disable cinemate-installer.service
    rm -f "$SERVICE_FILE"
    echo "Installation complete." > "$INSTALL_DIR/done"
}

# ---------------------------------------------------------------
# Main execution: run steps based on saved state
# ---------------------------------------------------------------
STEP=$(load_state)
case "$STEP" in
  0)
    ensure_service
    save_state 1
    reboot
    ;;
  1)
    step_install_base_packages
    save_state 2
    ;;
  2)
    step_install_libcamera
    save_state 3
    ;;
  3)
    step_libcamera_utils_permissions
    save_state 4
    ;;
  4)
    step_fix_libtiff
    save_state 5
    ;;
  5)
    step_extra_dependencies
    save_state 6
    ;;
  6)
    step_install_nvm
    save_state 7
    ;;
  7)
    step_install_cpp_mjpeg_streamer
    save_state 8
    ;;
  8)
    step_cinepi_raw_deps
    save_state 9
    ;;
  9)
    step_build_cinepi_raw
    save_state 10
    ;;
  10)
    step_python_venv
    save_state 11
    ;;
  11)
    step_grant_sudo_i2c
    save_state 12
    reboot
    ;;
  12)
    step_cinemate_deps
    save_state 13
    ;;
  13)
    step_replace_rpi_gpio
    save_state 14
    ;;
  14)
    step_clone_cinemate
    save_state 15
    ;;
  15)
    step_allow_main_sudo
    save_state 16
    ;;
  16)
    step_enable_network_manager
    save_state 17
    ;;
  17)
    step_rotate_logs
    save_state 18
    ;;
  18)
    step_seed_redis
    save_state 19
    ;;
  19)
    step_alias_bashrc
    save_state 20
    ;;
  20)
    step_make_install
    save_state 21
    ;;
  21)
    step_install_services
    save_state 22
    reboot
    ;;
  22)
    step_cleanup
    ;;
esac
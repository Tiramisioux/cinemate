# WiFi Hotspot Service for Raspberry Pi / Cinemate

This service creates and maintains a Wi-Fi hotspot on the Raspberry Pi (compatible with both Pi 4 and 5). The hotspot will be automatically created on boot and recreated if it goes down.

## Features

- Creates a Wi-Fi hotspot named "cinepi"
- Uses the password "11111111"
- Automatically starts on boot
- Continuously monitors and recreates the hotspot if it goes down

## Prerequisites

- You have already cloned the cinemate repository, which includes this WiFi hotspot service in the `/services` directory.

## Installation

You can install the WiFi hotspot service using the following one-liner:

```bash
sudo cp /home/pi/cinemate/services/wifi-hotspot/wifi_hotspot_service.py /home/pi/cinemate/src/module/ && sudo chmod +x /home/pi/cinemate/src/module/wifi_hotspot_service.py && sudo cp /home/pi/cinemate/services/wifi-hotspot/wifi-hotspot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable wifi-hotspot.service && sudo systemctl start wifi-hotspot.service
```

This command does the following:
1. Copies the Python script to the appropriate location
2. Makes the script executable
3. Copies the service file to the systemd directory
4. Reloads the systemd daemon
5. Enables the service to start on boot
6. Starts the service

## Verifying the Installation

To check if the service is running correctly:

1. Check the status of the service:
   ```
   sudo systemctl status wifi-hotspot.service
   ```

2. View the service logs:
   ```
   sudo journalctl -u wifi-hotspot.service
   ```

## Troubleshooting

If you encounter any issues:

1. Make sure your Raspberry Pi's Wi-Fi interface is not being used by another service.
2. Check the system logs for any error messages:
   ```
   sudo journalctl -u wifi-hotspot.service
   ```
3. Ensure that the necessary permissions are set for the script and service file.
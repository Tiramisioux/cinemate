### Simple GUI

![Cinemate Web App](../images/cinemate-webb-app.png)

The Simple GUI of CineMate provides an intuitive interface on the HDMI display, allowing users to control and monitor various camera settings in real-time. The interface is designed to be user-friendly, offering quick access to essential functions and real-time feedback on camera performance.

**Key Features of the Simple GUI:**

- **ISO Control**: Adjust the ISO setting to control the camera's sensitivity to light.
- **Shutter Angle**: Modify the shutter angle to control the exposure time.
- **Frame Rate (FPS)**: Set the desired frames per second for video recording.
- **White Balance (WB)**: Choose the appropriate white balance setting for accurate color representation.
- **Recording Time**: Display the remaining recording time.
- **System Metrics**: Monitor the CPU usage, RAM usage, and temperature of the Raspberry Pi.
- **Unmount Button**: Safely unmount the connected SSD or storage device.
- **Camera Model and Resolution**: Show the current camera model and resolution settings.
- **Enter Fullscreen**: Option to view the interface in fullscreen mode for an immersive experience.

The interface is designed to be straightforward, making it easy for users to make quick adjustments without navigating through complex menus.

### Web App

The Web App in CineMate extends the functionality of the Simple GUI by providing remote access to camera controls via a web browser. This allows users to control the camera and monitor its settings from any device connected to the same network.

**Key Features of the Web App:**

- **Real-Time Control**: Adjust ISO, shutter angle, FPS, and white balance settings remotely.
- **Live Preview**: View the camera feed in real-time, providing immediate feedback on adjustments.
- **System Monitoring**: Keep track of system metrics such as CPU usage, RAM usage, and temperature.
- **Remote Access**: Control the camera from a laptop, tablet, or smartphone without needing to be physically close to the Raspberry Pi.
- **User-Friendly Interface**: The web interface mirrors the simplicity of the Simple GUI, ensuring a consistent user experience across different platforms.

**Connecting to the Web App:**

1. **Enable WiFi on Your Device**:
   - Open the WiFi settings on your device (laptop, smartphone, or tablet).

2. **Find the Cinemate Hotspot**:
   - Look for a network named "CinemateHotspot" in the list of available WiFi networks.

3. **Connect to the Hotspot**:
   - Select the "CinemateHotspot" network and connect to it. If prompted for a password, enter the password provided with your Cinemate device.

4. **Access the Web Interface**:
   - Once connected to the hotspot, open a web browser and navigate to the default IP address for the Cinemate interface (e.g., `http://192.168.4.1`).

5. **Start Using Cinemate**:
   - You can now control the Cinemate system directly from your device. Use the web interface to manage media playback and other settings.

### Example Screenshot of the Web App

Below is an example screenshot of the CineMate Web App interface, showing the various controls and real-time feedback features:

![Cinemate Web App](../images/cinemate-webb-app.png)

This image illustrates the user-friendly layout of the web app, which includes controls for ISO, shutter angle, FPS, and white balance, as well as real-time system metrics and live camera feed.

### Conclusion

The Simple GUI and Web App in CineMate provide powerful yet easy-to-use interfaces for controlling and monitoring your Raspberry Pi-based cinema camera. Whether you are working directly with the camera or remotely via the web app, these tools offer the flexibility and functionality needed to achieve professional results.
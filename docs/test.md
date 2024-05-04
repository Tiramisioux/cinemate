# OneInchEye Quick Start Guide

This quick start guide will help you set up and start using your OneInchEye camera board for Raspberry Pi Compute Module 4. Please follow the steps outlined below to set up and start using your camera board.
The following guide has updated for bookworm.

## 1. Verify Compatibility

Make sure your Raspberry Pi Compute Module 4 board has a 22-pin FPC connector with the same pinout as the Raspberry Pi Compute Module 4 IO Board's CAM1 port.

## 2. Assemble the Hardware

1. Attach the OneInchEye camera board to the Raspberry Pi Compute Module 4 board using the 22-pin FPC connector to CAM1 connector. The FPC contact should face up rather then down. FPC Guide
2Ensure that the camera board is s. ecurely connected and that the pins are properly aligned.

## Set Up the Operating System

Download and flash the latest 64bit Raspberry Pi OS for your Compute Module 4 board.
Insert the microSD card (with the flashed OS) into your Raspberry Pi Compute Module 4 board.
4. Power Up the Raspberry Pi

Connect your Raspberry Pi Compute Module 4 board to a power source and boot up the operating system.
Compile and Install the Camera Driver

## 5. Setting Up the Tools

First, install the necessary tools (linux-headers, dkms, and git):

```sudo apt install linux-headers dkms git```

6. Fetching the Source Code, Compiling and Installing the Kernel Driver

Clone the repository to your local pi and navigate to the cloned directory:

```
git clone https://github.com/will127534/imx283-v4l2-driver.git
```

```
cd imx283-v4l2-driver/
To compile and install the kernel driver, execute the provided installation script:
```

sudo ./setup.sh
7. Updating the Boot Configuration


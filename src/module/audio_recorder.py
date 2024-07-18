# Raspberry Pi code (Python)
import RPi.GPIO as GPIO
import pyaudio
import wave
import time
import os

# Set up GPIO to read the clock signal from the Pico
GPIO.setmode(GPIO.BCM)
clock_pin = 18
GPIO.setup(clock_pin, GPIO.IN)

# Callback function to handle the clock signal
def clock_callback(channel):
    global recording
    if recording:
        # This is where you handle the timing for audio recording
        # For demonstration, we will print a message
        print("Clock signal received")

# Set up interrupt to detect clock signal
GPIO.add_event_detect(clock_pin, GPIO.RISING, callback=clock_callback)

# Set up audio recording
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10
SAVE_DIRECTORY = "/media/RAW"
WAVE_OUTPUT_FILENAME = "output.wav"

audio = pyaudio.PyAudio()

# List all available audio devices
info = audio.get_host_api_info_by_index(0)
numdevices = info.get('deviceCount')
print("Available audio devices:")
for i in range(0, numdevices):
    if (audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        print(f"Input Device id {i} - {audio.get_device_info_by_host_api_device_index(0, i).get('name')}")

# Set the device index of your USB microphone here
device_index = 1  # Change this to the correct index

# Start recording
stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, input_device_index=device_index,
                    frames_per_buffer=CHUNK)

print("Recording...")

frames = []

recording = True
start_time = time.time()

try:
    while time.time() - start_time < RECORD_SECONDS:
        data = stream.read(CHUNK)
        frames.append(data)
except KeyboardInterrupt:
    pass

print("Finished recording")

# Stop recording
recording = False
stream.stop_stream()
stream.close()
audio.terminate()

# Save the recorded data to a file if the directory exists
if os.path.exists(SAVE_DIRECTORY):
    file_path = os.path.join(SAVE_DIRECTORY, WAVE_OUTPUT_FILENAME)
    wf = wave.open(file_path, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"File saved to {file_path}")
else:
    print(f"Directory {SAVE_DIRECTORY} does not exist. File not saved.")

# Clean up GPIO
GPIO.cleanup()

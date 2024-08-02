import RPi.GPIO as GPIO
import subprocess
import time

# GPIO pin for PWM signal
PWM_PIN = 18

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PWM_PIN, GPIO.IN)

# Sample rate for recording (2x the PWM frequency)
SAMPLE_RATE = 16000

# Duration for recording in seconds
RECORD_DURATION = 10

# File to save the recorded audio
AUDIO_FILE = 'synced_audio.wav'

def record_audio():
    """Record audio using arecord at the specified sample rate."""
    command = [
        'arecord',
        '-D', 'plughw:2,0',
        '-f', 'cd',
        '-r', str(SAMPLE_RATE),
        '-d', str(RECORD_DURATION),
        AUDIO_FILE
    ]
    subprocess.run(command)

def sync_recording():
    """Wait for the PWM signal to sync and start recording."""
    try:
        print("Waiting for PWM signal to sync...")
        # Wait for a rising edge on the PWM pin
        GPIO.wait_for_edge(PWM_PIN, GPIO.RISING)
        print("PWM signal detected. Starting recording...")
        # Start recording audio
        record_audio()
    except KeyboardInterrupt:
        print("Recording interrupted.")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    sync_recording()
    print(f"Recording saved to {AUDIO_FILE}")

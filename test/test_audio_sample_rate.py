import subprocess
import wave
import contextlib
import time
import os

# List of sample rates to test
sample_rates = [47952, 47892, 47880, 47863, 47858, 47855, 47846, 48000]

# Recording duration in seconds
record_seconds = 10

# Set correct ALSA device
default_device = "hw:0,0"

# Audio format
audio_format = "S16_LE"
channels = 1

# Output directory
output_dir = "audio_rate_tests"
os.makedirs(output_dir, exist_ok=True)

def record_wav(rate, filename):
    cmd = [
        "arecord",
        "-D", default_device,
        "-f", audio_format,
        "-c", str(channels),
        "-r", str(rate),
        "-d", str(record_seconds),
        "-t", "wav",
        filename
    ]
    print(f"Recording at {rate} Hz for {record_seconds} sec...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] arecord failed for {rate} Hz:")
        print(result.stderr)
        return False
    return True

def get_duration_wav(filename):
    with contextlib.closing(wave.open(filename, 'r')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)
        return frames, rate, duration

# Main loop
results = []
for rate in sample_rates:
    fname = os.path.join(output_dir, f"test_{rate}.wav")
    if not record_wav(rate, fname):
        print(f"Skipping {rate} Hz due to error.")
        continue
    if not os.path.exists(fname):
        print(f"[ERROR] File not created: {fname}")
        continue
    frames, actual_rate, duration = get_duration_wav(fname)
    drift = duration - record_seconds
    results.append((rate, frames, actual_rate, duration, drift))
    print(f"SampleRate: {rate}, Frames: {frames}, Duration: {duration:.3f} sec, Drift: {drift:.3f} sec")

# Summary
print("\n=== Summary ===")
print("Rate     | Frames   | Duration  | Drift")
for rate, frames, actual_rate, duration, drift in results:
    print(f"{rate:<8} {frames:<9} {duration:.3f} sec  {drift:.3f} sec")
import re

def analyze_logs(logfile):
    with open(logfile, 'r') as file:
        logs = file.readlines()

    framerates = []
    frequencies = []
    adjustments = []
    errors = []
    integrals = []
    derivatives = []
    frame_counts = []
    expected_frames_list = []

    for line in logs:
        if "Smoothed framerate" in line:
            framerate = float(re.findall(r"Smoothed framerate: (\d+\.\d+)", line)[0])
            framerates.append(framerate)
        elif "New Frequency" in line:
            frequency = float(re.findall(r"New Frequency: (\d+\.\d+)", line)[0])
            frequencies.append(frequency)
        elif "PID Adjustment" in line:
            adjustment = float(re.findall(r"PID Adjustment: (-?\d+\.\d+)", line)[0])
            adjustments.append(adjustment)
        elif "PID Controller" in line:
            error = float(re.findall(r"error=(-?\d+\.\d+)", line)[0])
            integral = float(re.findall(r"integral=(-?\d+\.\d+)", line)[0])
            derivative = float(re.findall(r"derivative=(-?\d+\.\d+)", line)[0])
            errors.append(error)
            integrals.append(integral)
            derivatives.append(derivative)
        elif "Recording stopped, frame count" in line:
            frame_count = int(re.findall(r"frame count: (\d+)", line)[0])
            expected_frames = float(re.findall(r"expected frames: (\d+\.\d+)", line)[0])
            frame_counts.append(frame_count)
            expected_frames_list.append(expected_frames)

    avg_framerate = sum(framerates) / len(framerates) if framerates else 0
    avg_frequency = sum(frequencies) / len(frequencies) if frequencies else 0

    print(f"Average Framerate: {avg_framerate:.5f}")
    print(f"Average Frequency: {avg_frequency:.5f}")

    if adjustments:
        avg_adjustment = sum(adjustments) / len(adjustments)
        print(f"Average Adjustment: {avg_adjustment:.5f}")
    else:
        print("No PID adjustments found in the log.")

    if errors:
        avg_error = sum(errors) / len(errors)
        max_error = max(errors)
        min_error = min(errors)
        print(f"Average Error: {avg_error:.5f}")
        print(f"Max Error: {max_error:.5f}")
        print(f"Min Error: {min_error:.5f}")
    else:
        print("No PID errors found in the log.")
        avg_error = None

    if integrals:
        avg_integral = sum(integrals) / len(integrals)
        max_integral = max(integrals)
        min_integral = min(integrals)
        print(f"Average Integral: {avg_integral:.5f}")
        print(f"Max Integral: {max_integral:.5f}")
        print(f"Min Integral: {min_integral:.5f}")
    else:
        print("No PID integrals found in the log.")
        avg_integral = None

    if derivatives:
        avg_derivative = sum(derivatives) / len(derivatives)
        max_derivative = max(derivatives)
        min_derivative = min(derivatives)
        print(f"Average Derivative: {avg_derivative:.5f}")
        print(f"Max Derivative: {max_derivative:.5f}")
        print(f"Min Derivative: {min_derivative:.5f}")
    else:
        print("No PID derivatives found in the log.")
        avg_derivative = None

    if frame_counts and expected_frames_list:
        total_frames_recorded = sum(frame_counts)
        total_expected_frames = sum(expected_frames_list)
        print(f"Total Frames Recorded: {total_frames_recorded}")
        print(f"Total Expected Frames: {total_expected_frames:.5f}")

    # Example recommendations based on simple heuristics
    recommendations = []

    kp, ki, kd = 0.12, 0.02, 0.06  # Current PID values

    if avg_error is not None:
        if avg_error > 0:
            kp *= 1.1  # Increase kp by 10%
            recommendations.append(f"Increase kp to {kp:.5f} to reduce the positive average error.")
        elif avg_error < 0:
            kp *= 0.9  # Decrease kp by 10%
            recommendations.append(f"Decrease kp to {kp:.5f} to reduce the negative average error.")

    if avg_integral is not None:
        if avg_integral < 0:
            ki *= 0.9  # Decrease ki by 10%
            recommendations.append(f"Slightly decrease ki to {ki:.5f} to reduce the overcompensation effect of the accumulated error.")
        elif avg_integral > 0:
            ki *= 1.1  # Increase ki by 10%
            recommendations.append(f"Slightly increase ki to {ki:.5f} to improve compensation for accumulated error.")

    if avg_derivative is not None and avg_derivative > 0.02:  # Arbitrary threshold for spike detection
        kd *= 1.1  # Increase kd by 10%
        recommendations.append(f"Increase kd to {kd:.5f} to dampen rapid changes in error.")

    if recommendations:
        print("\nRecommendations:")
        for recommendation in recommendations:
            print(f"- {recommendation}")

    # Print new suggested values
    print(f"\nSuggested PID values:")
    print(f"kp: {kp:.5f}")
    print(f"ki: {ki:.5f}")
    print(f"kd: {kd:.5f}")

    return kp, ki, kd

if __name__ == "__main__":
    analyze_logs("/home/pi/cinemate/src/logs/system.log")

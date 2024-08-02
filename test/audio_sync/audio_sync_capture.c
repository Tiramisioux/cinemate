#include "audio_sync_capture.h"

// Initialize GPIO for PWM input
int init_gpio(int pin) {
    if (wiringPiSetupGpio() == -1) {
        fprintf(stderr, "Failed to initialize wiringPi\n");
        return -1;
    }
    pinMode(pin, INPUT);
    return 0;
}

// Initialize ALSA PCM device for audio capture
int init_pcm(snd_pcm_t **pcm_handle, snd_pcm_hw_params_t **params) {
    int dir;
    snd_pcm_uframes_t frames = FRAMES;
    int err;

    // Open PCM device for recording (capture)
    if ((err = snd_pcm_open(pcm_handle, "default", SND_PCM_STREAM_CAPTURE, 0)) < 0) {
        fprintf(stderr, "Error opening PCM device: %s\n", snd_strerror(err));
        return err;
    }

    // Allocate a hardware parameters object
    snd_pcm_hw_params_alloca(params);

    // Fill it in with default values
    snd_pcm_hw_params_any(*pcm_handle, *params);

    // Set the desired hardware parameters
    // Interleaved mode
    snd_pcm_hw_params_set_access(*pcm_handle, *params, SND_PCM_ACCESS_RW_INTERLEAVED);

    // Signed 16-bit little-endian format
    snd_pcm_hw_params_set_format(*pcm_handle, *params, SND_PCM_FORMAT_S16_LE);

    // Set channels
    snd_pcm_hw_params_set_channels(*pcm_handle, *params, CHANNELS);

    // Set sample rate
    unsigned int sample_rate = SAMPLE_RATE;
    snd_pcm_hw_params_set_rate_near(*pcm_handle, *params, &sample_rate, &dir);

    // Set period size
    snd_pcm_hw_params_set_period_size_near(*pcm_handle, *params, &frames, &dir);

    // Write the parameters to the driver
    if ((err = snd_pcm_hw_params(*pcm_handle, *params)) < 0) {
        fprintf(stderr, "Unable to set HW parameters: %s\n", snd_strerror(err));
        return err;
    }

    return 0;
}

// Record audio using ALSA PCM device
int record_audio(snd_pcm_t *pcm_handle, int duration, const char *filename) {
    int err;
    int size;
    snd_pcm_hw_params_t *params;
    snd_pcm_uframes_t frames = FRAMES;
    char *buffer;

    // Get the parameters of the PCM device
    snd_pcm_hw_params_alloca(&params);
    snd_pcm_hw_params_current(pcm_handle, params);

    // Use a buffer large enough to hold one period
    snd_pcm_hw_params_get_period_size(params, &frames, &err);
    size = frames * 2; // 2 bytes/sample, 1 channel
    buffer = (char *)malloc(size);

    if (buffer == NULL) {
        fprintf(stderr, "Buffer allocation error\n");
        return -1;
    }

    FILE *output_file = fopen(filename, "wb");
    if (output_file == NULL) {
        fprintf(stderr, "Error opening file '%s'\n", filename);
        free(buffer);
        return -1;
    }

    // Record for the specified duration
    int total_frames = SAMPLE_RATE * duration;
    int frames_recorded = 0;
    while (frames_recorded < total_frames) {
        int frames_to_capture = frames;
        if (frames_to_capture > total_frames - frames_recorded) {
            frames_to_capture = total_frames - frames_recorded;
        }

        if ((err = snd_pcm_readi(pcm_handle, buffer, frames_to_capture)) != frames_to_capture) {
            fprintf(stderr, "Read from PCM device failed: %s\n", snd_strerror(err));
            break;
        }

        fwrite(buffer, size, 1, output_file);
        frames_recorded += frames_to_capture;
    }

    fclose(output_file);
    free(buffer);

    return 0; // Ensure a proper return statement is provided
}

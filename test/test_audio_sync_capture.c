#include "audio_sync_capture.h"
#include <stdio.h>

int main() {
    snd_pcm_t *pcm_handle;
    const char *filename = "test_output.wav";
    int duration = 5; // Duration in seconds

    // Initialize ALSA PCM device
    if (init_pcm(&pcm_handle) != 0) {
        fprintf(stderr, "Error initializing PCM device\n");
        return -1;
    }

    // Record audio
    if (record_audio(pcm_handle, duration, filename) != 0) {
        fprintf(stderr, "Error recording audio\n");
        return -1;
    }

    // Cleanup
    snd_pcm_close(pcm_handle);

    printf("Audio recording complete, saved to %s\n", filename);
    return 0;
}

#ifndef AUDIO_SYNC_CAPTURE_H
#define AUDIO_SYNC_CAPTURE_H

#include <stdio.h>
#include <stdlib.h>
#include <alsa/asoundlib.h>
#include <wiringPi.h>

// Constants
#define SAMPLE_RATE 48000  // 48 kHz
#define CHANNELS 1         // Mono
#define FRAMES 32          // Frames per period

// Function prototypes
int init_gpio(int pin);
int init_pcm(snd_pcm_t **pcm_handle, snd_pcm_hw_params_t **params);
int record_audio(snd_pcm_t *pcm_handle, int duration, const char *filename);
void cleanup(snd_pcm_t *pcm_handle);

#endif // AUDIO_SYNC_CAPTURE_H

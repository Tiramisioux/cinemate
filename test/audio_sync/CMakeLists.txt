cmake_minimum_required(VERSION 3.10)
project(audio_sync)

set(CMAKE_C_STANDARD 11)

add_library(audio_sync_capture SHARED audio_sync_capture.c)

# Link any required libraries (e.g., ALSA)
target_link_libraries(audio_sync_capture asound)

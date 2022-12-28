#!/usr/bin/python
import time
import RPi.GPIO as GPIO
from signal import pause
from time import sleep
from datetime import datetime
import os, glob
from controls import CameraParameters
from os.path import exists

ledPin = 20

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(ledPin, GPIO.IN)

fps_base = 24

iso = CameraParameters("ISO")
shutter_angle = CameraParameters("SHUTTER")
fps = CameraParameters("FPS")

path = "/media/RAW"

def timestamp_to_TC(timestamp):
    h = int(timestamp.strftime("%H"))
    m = int(timestamp.strftime("%M"))
    s = int(timestamp.strftime("%S"))
    f = round(int(timestamp.strftime("%f"))/1000000*fps_base)
    return ( "%02d:%02d:%02d:%02d" % ( h, m, s, f))

def frames_to_TC (frames):                                      # Returns frame number as an hh:mm:ss:frames-string
    h = int(frames / 86400)                                     # https://gist.github.com/schiffty/c838db504b9a1a7c23a30c366e8005e8
    m = int(frames / 1440) % 60 
    s = int((frames % 1440)/24) 
    f = frames % 1440 % 24
    return ( "%02d:%02d:%02d:%02d" % ( h, m, s, f))

def TC_to_frames (timecode_string):                             # Returns a hh:mm:ss:frames-string as frame number integer
    hh = int(timecode_string[0:2])
    mm = int(timecode_string[3:5])
    ss = int(timecode_string[6:8])
    frames = int(timecode_string[9:11])
    return int(((hh * 3600 * 24 + mm * 60 + ss) * fps_base) + frames)

def last_line(filename):
    with open(filename, "r") as file:            
        lines=file.readlines()
    last_line = lines[-3]
    return last_line

def rec_detect(channel):
    global rec_start_timestamp, rec_stop_timestamp
    
    if GPIO.input(ledPin):
        rec_start_timestamp = datetime.now()
        time_entry_start = timestamp_to_TC(rec_start_timestamp)
        print("recording started ", time_entry_start)

    if not GPIO.input(ledPin):
        rec_stop_timestamp = datetime.now()
        time_entry_stop = timestamp_to_TC(rec_stop_timestamp)
        iso_n = iso.get()
        shutter_angle_n = shutter_angle.get()
        fps_n = fps.get()
        
        last_directory = max([os.path.join(path,d) for d in os.listdir(path)], key=os.path.getmtime)
        clip_name = last_directory[11:31]
        file_list = os.listdir(last_directory)
        frame_count_files = len(file_list)
        frame_count_tc = TC_to_frames(timestamp_to_TC(rec_start_timestamp)) - TC_to_frames(timestamp_to_TC(rec_stop_timestamp))

        if abs(frame_count_files + frame_count_tc) > 2:
            flag = "Pink"
        else:
            flag = "None"
        
        #check if files exist, otherwise create them
        
        metadata_exists = exists("/media/RAW/metadata.csv")
        edl_exists = exists("/media/RAW/edl.edl")
        
        if not metadata_exists:
            with open("/media/RAW/metadata.csv", "w") as f:
                f.write("File Name,Date_Recorded,Start TC,FPS,Camera_Type,Camera_ID,Camera_FPS,Shutter,ISO,Camera_Notes,Flags"
                        + "\n")
                f.close()
                
        if not edl_exists:
            with open("/media/RAW/edl.edl", "w") as f:
                f.write("TITLE: EDL"
                        + "\n" 
                        + "FCM: NON-DROP FRAME"
                        + "\n"
                        + "\n")
                f.close()
            last_event = 0

        #check last event number in edl
        if edl_exists:
            line = last_line("/media/RAW/edl.edl")
            last_event = int(line[0:3])

        #Metadata for DaVinci
        Clip_Name = str(clip_name + "_frame_[000000-" + '{:06}'.format(frame_count_files-1) + "].dng")
        Date_Recorded = str(rec_start_timestamp.strftime("%c"))
        Start_TC = str(timestamp_to_TC(rec_start_timestamp))
        FPS = str(fps_base)
        Camera_Type = "CinePi 2K"
        Camera_ID = str(clip_name[0:1])
        Camera_FPS = str(fps_n)
        Shutter = str(shutter_angle_n[1])
        ISO = str(round(iso_n))
        Camera_Notes = "EXPOSURE: 1/" + str(shutter_angle_n[0])
        Flags = str(flag)
        
        #Metadata for EDL
        event_id = '{:03}'.format(last_event+1)
        source_TC_in = timestamp_to_TC(rec_start_timestamp)
        source_TC_out = timestamp_to_TC(rec_stop_timestamp)
        record_TC_in = timestamp_to_TC(rec_start_timestamp)
        record_TC_out = timestamp_to_TC(rec_stop_timestamp)
        
        print("recording stopped ", time_entry_stop, round(iso_n), shutter_angle_n[0], shutter_angle_n[1], round(shutter_angle_n[2],4), fps_n, clip_name, frame_count_files, frame_count_tc, event_id, flag)
        
        #write metadata to metadata.csv
        with open("/media/RAW/metadata.csv", "a") as f:
            f.write(
                str(Clip_Name + "," + Date_Recorded + "," + Start_TC + "," + FPS + "," + Camera_Type + "," + Camera_ID + "," + Camera_FPS + "," + Shutter + "," + ISO + "," + Camera_Notes + "," + Flags + "\n")
            )
            f.close()
        
        #write metadata to edl.edl
        with open("/media/RAW/edl.edl", "a") as f:
            f.write(
                str(event_id + " AX       V     C        " + source_TC_in + " " + source_TC_out + " " + record_TC_in + " " + record_TC_out + "\n"
                    + "* FROM CLIP NAME: " + Clip_Name + "\n"
                    + "\n")    
                    )
            f.close()
    
GPIO.add_event_detect(ledPin, GPIO.BOTH, callback=rec_detect)

pause()


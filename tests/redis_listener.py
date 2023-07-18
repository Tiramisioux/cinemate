import redis
import re
from datetime import datetime

class RedisListener:
    def __init__(self, channel):
        self.redis = redis.Redis(host='localhost', port=6379)
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(channel)

        self.frame_count = None
        self.fps_actual = None
        self.data_list = []
        self.start_time = None
        self.start_counting = False
        
        self.is_increasing = False  # Added this line

        print("Starting listener...")
        self.run()

    def run(self):
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = message['data'].decode('utf-8')  # decode byte string to string
                self.analyze_message(data)

    def analyze_message(self, data):
        if re.match(r"^\d{1,2}\.\d{6}$", data):  # matches 7 digit float e.g., "0.999942"
            self.fps_actual = float(data)

        elif re.match(r"^F:\d+$", data):  # matches pattern "F:number" e.g., "F:480"
            self.analyze_frame_count(int(data[2:]))

    def analyze_frame_count(self, new_frame_count):
        if self.frame_count is None:
            if new_frame_count > 0:  # Start of the frame count increment
                self.start_counting = True
                self.start_time = datetime.now().strftime("%y-%m-%d_%H%M%S")
                self.is_increasing = True  # Set the flag to True when frame count starts increasing
            self.frame_count = new_frame_count
            self.data_list.append((self.fps_actual, self.frame_count))
        elif new_frame_count > self.frame_count:  # self.frame_count is not None here
            if not self.start_counting:
                self.start_counting = True
                self.start_time = datetime.now().strftime("%y-%m-%d_%H%M%S")
            self.frame_count = new_frame_count
            self.data_list.append((self.fps_actual, self.frame_count))
            self.is_increasing = True  # Set the flag to True when frame count is still increasing
        elif self.start_counting and new_frame_count <= self.frame_count and self.data_list:  
            self.save_data()
            self.frame_count = new_frame_count
            self.start_counting = False
            self.is_increasing = False  # Set the flag to False when frame count stops increasing


    def save_data(self):
        filename = f"/media/RAW/CINEPI_{self.start_time}_PTS_DATA.txt"
        with open(filename, "w") as file:
            for i in range(len(self.data_list) - 1):
                fps, _ = self.data_list[i]
                _, next_frame_count = self.data_list[i + 1]
                if fps and fps != 0:  # ensure fps is not None or zero before dividing by it
                    timestamp = round((1 / fps) * next_frame_count * 1000)
                    file.write(f"{timestamp}\n")
                else:
                    print(f"Skipping calculation for iteration {i} due to zero or None fps value.")
        print(f"Saved PTS-file {filename}")
        self.data_list = []  # reset the list
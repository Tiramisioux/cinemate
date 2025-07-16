# Redis API quick start

You can think of the toolchain like this:

camera sensor > libcamera > cinepi-raw <> redis <> cinemate

> It is a bit more complicated than that but in the context of describing redis and Cinemate it is pretty accurate

- Cinemate talks to the [cinepi-raw](https://github.com/Tiramisioux/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder) recorder through a local Redis server. 
- Parameters such as ISO, FPS or the recording state are stored as simple keys. 
- Two pub-sub channels (`cp_controls` and `cp_stats`) carry notifications and status updates.

## The `cp_controls` channel

Both cinepi-raw and CineMate writes values and immediately publish the key name. The recorder only reacts when it receives that publish event. 

Any key may be sent this way. For example, to adjust the preview zoom:

```bash
# Set preview zoom level

redis-cli SET zoom 1.5
redis-cli PUBLISH cp_controls zoom
```

>Execpt for the recording trigger __is_recording__. Here, the Cinemate cinepi-raw fork _immediately_ starts and stops recording upon edge detection (the variable changes from 0 to 1 or vice versa). The reason  for this exception has to do with how the cinepi-raw fork handles recording with multiple cameras


```bash
# Start recording
redis-cli SET is_recording 1                    # triggers 0 → 1 edge

# Stop recording
redis-cli SET is_recording 0                    # triggers 1 → 0 edge
```

## The `cp_stats` channel

Every frame, cinepi-raw sends a small JSON object containing live statistics. 

```cpp
    Json::Value data;
    Json::Value histo;
    data["framerate"] = completed_request->framerate;
    data["colorTemp"] = info.colorTemp;
    data["focus"] = info.focus;
    data["frameCount"] = app_->GetEncoder()->getFrameCount();
    data["bufferSize"] = app_->GetEncoder()->bufferSize();
    redis_->publish(CHANNEL_STATS, data.toStyledString());
```

CineMate’s `RedisListener` parses these messages and updates Redis keys like `framecount`, `BUFFER` and `fps_actual`.

## Inspecting and changing values with `redis-cli`

Because everything is plain Redis you can poke around from the command line. Here are a few handy commands:

```bash
# List all keys
redis-cli KEYS '*'

# Read the current ISO value
redis-cli GET iso

# Start a recording (same as pressing the Rec button)
redis-cli SET is_recording 1
redis-cli PUBLISH cp_controls is_recording
```

## Controlling the camera from your own script

Below is a very small example using `redis-py`. This is basically what Cinemate does: it keeps track of variables  being set by cinepi-raw, and also setting the same, or other variable by itself.



```python
import redis
r = redis.Redis(host='localhost', port=6379, db=0)

# toggle recording
current = r.get('is_recording')
new_value = b'0' if current == b'1' else b'1'
r.set('is_recording', new_value)
r.publish('cp_controls', 'is_recording')
```

Note that in this example, the publishing of the is_recording key is not strictly needed for recording to start/stop, but for formality's sake I think we should keep the publish command.



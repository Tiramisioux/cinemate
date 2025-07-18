# Redis API quick start

## Redis-cli

```bash
# List all keys
redis-cli KEYS '*'

# Read the current ISO value
redis-cli GET iso

# Start a recording (same as pressing the Rec button)
redis-cli SET is_recording 1
redis-cli PUBLISH cp_controls is_recording
```

You can also type:

```shell
redis-cli
```

This will open the redis cli.

## cp_controls

Both CinePi-raw and Cinemate writes values and immediately publish the key name. The recorder only reacts when it receives that publish event. 

Any key may be sent this way. For example, to adjust the preview zoom:

```bash
# Set preview zoom level

redis-cli SET zoom 1.5
redis-cli PUBLISH cp_controls zoom
```

>Note that for the __is_recording__ key Cinemate stops recording upon edge detection (the variable changes from 0 to 1 or vice versa). The reason for this exception has to do with how the CinePi-raw fork handles recording with multiple cameras


```bash
# Start recording
redis-cli SET is_recording 1                    # triggers 0 → 1 edge

# Stop recording
redis-cli SET is_recording 0                    # triggers 1 → 0 edge
```

## cp_stats

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

## Controlling the camera from your own script

Below is a very small example using `redis-py`. 


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

!!! info
    
    This is basically what Cinemate does: it keeps track of variables being set by cinepi-raw, and also sets variables itself.




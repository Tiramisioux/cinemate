from flask import Flask, render_template_string, jsonify, request
import redis

app = Flask(__name__)

# Redis configuration
redis_host = 'localhost'
redis_port = 6379
redis_db = 0

# Example Redis controller class (adjust based on your actual implementation)
class RedisController:
    def __init__(self):
        self.redis_conn = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db)

    def get_value(self, key):
        return self.redis_conn.get(key).decode('utf-8') if self.redis_conn.exists(key) else None

    def set_value(self, key, value):
        self.redis_conn.set(key, value)

    def publish_message(self, channel, message):
        self.redis_conn.publish(channel, message)

# Mock RedisController instance (replace with your actual initialization logic)
redis_controller = RedisController()

# Your MJPEG stream URL
stream_url = "http://cinepi.local:8000/stream"

# HTML template with dynamic data overlay and dropdown menu
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MJPEG Stream with Overlay</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #000;
            font-family: 'Arial', sans-serif; /* Set custom font family */
        }
        #stream-container {
            position: relative;
            width: 80%; /* Adjust width as needed */
            height: 0;
            padding-bottom: 56.25%; /* 16:9 aspect ratio */
            overflow: hidden;
            margin: auto;
        }
        #stream {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain; /* Ensure the stream fits within its container */
        }
        #overlay {
            position: absolute;
            top: 10px;
            left: 10px;
            color: #fff;
            font-size: 24px;
            background: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 10px;
            cursor: pointer; /* Change cursor to pointer for better UX */
        }
        #iso-dropdown {
            display: none;
            position: absolute;
            top: 50px;
            left: 10px;
            background: rgba(0, 0, 0, 0.8);
            padding: 10px;
            border-radius: 5px;
            z-index: 1000;
        }
        #iso-dropdown.show {
            display: block;
        }
        #iso-dropdown select {
            width: 100%;
            padding: 8px;
            font-size: 16px;
            border: none;
            background-color: #333;
            color: #fff;
            border-radius: 5px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div id="stream-container">
        <img id="stream" src="{{ stream_url }}" alt="Stream">
    </div>
    <div id="overlay">ISO: {{ dynamic_data.iso }}</div>
    <div id="iso-dropdown">
        <select id="iso-select">
            <option value="100">100</option>
            <option value="400">400</option>
            <option value="800">800</option>
            <option value="1600">1600</option>
        </select>
    </div>
    <button id="fullscreen-btn">Enter Fullscreen</button>
    <script>
        function fetchISO() {
            // Replace '/iso_value' with your actual endpoint to fetch ISO value
            fetch('/iso_value')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('overlay').innerText = `ISO: ${data.iso}`;
                })
                .catch(error => {
                    console.error('Error fetching ISO value:', error);
                });
        }

        // Fetch ISO value initially and set interval to update every 1 second
        fetchISO();
        setInterval(fetchISO, 1000); // Update ISO every 1 second
        
        // Add event listener for clicking on overlay to show dropdown
        document.getElementById('overlay').addEventListener('click', function() {
            document.getElementById('iso-dropdown').classList.toggle('show');
        });

        // Add event listener for selecting ISO from dropdown
        document.getElementById('iso-select').addEventListener('change', function() {
            const selectedIso = this.value;
            fetch('/set_iso', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ iso: selectedIso }),
            })
            .then(response => response.json())
            .then(data => {
                console.log('ISO set successfully:', data);
                // Optionally update UI or provide feedback
            })
            .catch(error => {
                console.error('Error setting ISO:', error);
                // Handle error as needed
            });
        });

        // Function to toggle full-screen mode
        function toggleFullScreen() {
            const elem = document.documentElement;

            if (!document.fullscreenElement && !document.webkitFullscreenElement && !document.msFullscreenElement) {
                // Enter full-screen mode
                if (elem.requestFullscreen) {
                    elem.requestFullscreen().catch(err => {
                        console.error('Error attempting to enable full-screen mode:', err.message);
                    });
                } else if (elem.webkitRequestFullscreen) { /* Safari */
                    elem.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT).catch(err => {
                        console.error('Error attempting to enable full-screen mode:', err.message);
                    });
                } else if (elem.msRequestFullscreen) { /* IE11 */
                    elem.msRequestFullscreen().catch(err => {
                        console.error('Error attempting to enable full-screen mode:', err.message);
                    });
                }
            } else {
                // Exit full-screen mode
                if (document.exitFullscreen) {
                    document.exitFullscreen().catch(err => {
                        console.error('Error attempting to exit full-screen mode:', err.message);
                    });
                } else if (document.webkitExitFullscreen) { /* Safari */
                    document.webkitExitFullscreen().catch(err => {
                        console.error('Error attempting to exit full-screen mode:', err.message);
                    });
                } else if (document.msExitFullscreen) { /* IE11 */
                    document.msExitFullscreen().catch(err => {
                        console.error('Error attempting to exit full-screen mode:', err.message);
                    });
                }
            }
        }

        // Add event listener for full-screen button
        document.getElementById('fullscreen-btn').addEventListener('click', function() {
            toggleFullScreen();
            updateFullscreenButton(); // Update button text immediately after click
        });

        // Detect changes in full-screen state and update button text accordingly
        document.addEventListener('fullscreenchange', updateFullscreenButton);
        document.addEventListener('webkitfullscreenchange', updateFullscreenButton);
        document.addEventListener('msfullscreenchange', updateFullscreenButton);

        function updateFullscreenButton() {
            const isInFullScreen = (document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement) !== null;
            const fullscreenBtn = document.getElementById('fullscreen-btn');

            if (isInFullScreen) {
                fullscreenBtn.textContent = 'Exit Fullscreen';
            } else {
                fullscreenBtn.textContent = 'Enter Fullscreen';
            }
        }
        
        // Detect touchstart to initiate full-screen on iOS
        document.getElementById('fullscreen-btn').addEventListener('touchstart', function(event) {
            event.preventDefault(); // Prevent the default behavior
            toggleFullScreen();
            updateFullscreenButton(); // Update button text immediately after touch
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    dynamic_data = {"iso": "Initializing..."}  # Initial data for ISO (replace with actual initialization logic)
    return render_template_string(html_template, stream_url=stream_url, dynamic_data=dynamic_data)

@app.route('/iso_value')
def get_iso_value():
    iso_value = redis_controller.get_value("iso")  # Fetch ISO value from Redis (adjust based on your implementation)
    return jsonify({"iso": iso_value})

@app.route('/set_iso', methods=['POST'])
def set_iso_value():
    iso = request.json.get('iso')
    if iso:
        redis_controller.set_value("iso", iso)
        redis_controller.publish_message("cp_controls", "iso")  # Publish ISO value to 'cp_controls'
        return jsonify({"status": "success", "iso": iso})
    else:
        return jsonify({"status": "error", "message": "ISO value not provided"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask_socketio import emit
import time

def register_events(socketio, redis_controller, cinepi_controller, simple_gui, sensor_detect):
    @socketio.on('connect')
    def handle_connect():
        initial_values = {
            'iso': redis_controller.get_value('iso'),
            'shutter_a': redis_controller.get_value('shutter_a'),
            'fps': redis_controller.get_value('fps'),
            'background_color': simple_gui.get_background_color()
        }
        
        # Include other dynamic values
        initial_values.update(simple_gui.populate_values())
        
        # Add sensor resolutions and current sensor model
        initial_values['sensor_resolutions'] = sensor_detect.get_available_resolutions()
        initial_values['current_sensor'] = sensor_detect.camera_model
        initial_values['selected_resolution_mode'] = redis_controller.get_value('sensor_mode')
        
        emit('initial_values', initial_values)

    def redis_change_handler(data):
        key = data['key']
        value = data['value']
        if key in ['iso', 'shutter_a', 'fps']:
            socketio.emit('parameter_change', {key: value})

    redis_controller.redis_parameter_changed.subscribe(redis_change_handler)

    @socketio.on('update_background_color')
    def handle_update_background_color():
        background_color = simple_gui.get_background_color()
        socketio.emit('background_color_change', {'background_color': background_color})

    @socketio.on('change_iso')
    def handle_change_iso(data):
        iso = data.get('iso')
        if iso:
            cinepi_controller.set_iso(int(iso))
            redis_controller.set_value('iso', iso)
            socketio.emit('parameter_change', {'iso': iso})

    @socketio.on('change_shutter_a')
    def handle_change_shutter_a(data):
        shutter_a = data.get('shutter_a')
        if shutter_a:
            cinepi_controller.set_shutter_a(float(shutter_a))
            redis_controller.set_value('shutter_a', shutter_a)
            socketio.emit('parameter_change', {'shutter_a': shutter_a})

    @socketio.on('change_fps')
    def handle_change_fps(data):
        fps = data.get('fps')
        if fps:
            cinepi_controller.set_fps(int(fps))
            redis_controller.set_value('fps', fps)
            socketio.emit('parameter_change', {'fps': fps})

    @socketio.on('change_resolution')
    def handle_change_resolution(data):
        sensor_mode = data.get('mode')
        if sensor_mode is not None:
            cinepi_controller.set_resolution(int(sensor_mode))
            redis_controller.set_value('sensor_mode', sensor_mode)
            socketio.emit('resolution_change', {'sensor_mode': sensor_mode})
            time.sleep(2)  # Add a 2-second pause
            socketio.emit('reload_browser')  # Emit event to reload the browser

    @socketio.on('container_tap')
    def handle_container_tap():
        cinepi_controller.rec()
        
    @socketio.on('gui_data_change')
    def handle_gui_data_change(data):
        emit('gui_data_change', data)
        
    @socketio.on('unmount')
    def handle_unmount():
        cinepi_controller.unmount()
        socketio.emit('unmount_complete')

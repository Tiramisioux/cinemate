import logging
from flask_socketio import emit
import time
from module.redis_controller import ParameterKey

def register_events(socketio, redis_controller, cinepi_controller, simple_gui, sensor_detect):
    
    @socketio.on('connect')
    def handle_connect():
        initial_values = {
            'iso': redis_controller.get_value(ParameterKey.ISO.value),
            'iso_steps': cinepi_controller.iso_steps,
            'shutter_a': redis_controller.get_value(ParameterKey.SHUTTER_A.value),
            'fps': redis_controller.get_value(ParameterKey.FPS_ACTUAL.value),
            'background_color': simple_gui.get_background_color(),
            'shutter_a_steps': cinepi_controller.shutter_a_steps_dynamic,
            'fps_steps': cinepi_controller.fps_steps_dynamic,
            'wb_steps': cinepi_controller.wb_steps,
            'wb': redis_controller.get_value(ParameterKey.WB.value) or (cinepi_controller.wb_steps[0] if cinepi_controller.wb_steps else None)
        }

        initial_values.update(simple_gui.populate_values())

        initial_values['sensor_resolutions'] = sensor_detect.get_available_resolutions()
        initial_values['current_sensor'] = sensor_detect.camera_model
        initial_values['selected_resolution_mode'] = redis_controller.get_value(ParameterKey.SENSOR_MODE.value)

        emit('initial_values', initial_values)

    def redis_change_handler(data):
        key = data['key']
        value = data['value']
        if key in [ParameterKey.ISO.value, ParameterKey.SHUTTER_A.value, ParameterKey.FPS_ACTUAL.value, ParameterKey.WB.value, ParameterKey.FRAMECOUNT.value, ParameterKey.BUFFER.value]:
            socketio.emit('parameter_change', {key: value})

        if key == ParameterKey.FPS_ACTUAL.value:
            # Emit the updated shutter_a_steps array and the current shutter speed
            shutter_a_steps = cinepi_controller.calculate_dynamic_shutter_angles(
                int(float(redis_controller.get_value(ParameterKey.FPS_ACTUAL.value)))
            )
            current_shutter_a = redis_controller.get_value(ParameterKey.SHUTTER_A.value)
            socketio.emit('shutter_a_update', {'shutter_a_steps': shutter_a_steps, 'current_shutter_a': current_shutter_a})

        if key in [ParameterKey.SENSOR_MODE.value, ParameterKey.WB.value]:
            time.sleep(2)  # Add a 2-second pause
            socketio.emit('reload_browser')  # Emit event to reload the browser

    redis_controller.redis_parameter_changed.subscribe(redis_change_handler)

    @socketio.on('update_background_color')
    def handle_update_background_color():
        background_color = simple_gui.get_background_color()
        socketio.emit('background_color_change', {'background_color': background_color})

    @socketio.on('change_framebuffer')
    def handle_change_framebuffer(data):
        framebuffer = data.get('framebuffer')
        if framebuffer:
            socketio.emit('parameter_change', {'framebuffer': framebuffer})
            print(emit)

    @socketio.on('change_iso')
    def handle_change_iso(data):
        iso = data.get('iso')
        if iso:
            cinepi_controller.set_iso(int(iso))
            socketio.emit('parameter_change', {'iso': iso})

    @socketio.on('change_shutter_a')
    def handle_change_shutter_a(data):
        shutter_a = data.get('shutter_a')
        if shutter_a:
            cinepi_controller.set_shutter_a(float(shutter_a))
            socketio.emit('parameter_change', {'shutter_a': shutter_a})
            # Emit the updated shutter_a_steps array and the current shutter speed
            shutter_a_steps = cinepi_controller.calculate_dynamic_shutter_angles(
                int(float(redis_controller.get_value(ParameterKey.FPS_ACTUAL.value)))
            )
            socketio.emit('shutter_a_update', {'shutter_a_steps': shutter_a_steps, 'current_shutter_a': shutter_a})

    @socketio.on('change_fps')
    def handle_change_fps(data):
        fps = data.get('fps')
        if fps:
            cinepi_controller.set_fps(int(fps))
            socketio.emit('parameter_change', {'fps': fps})
            # Emit the updated shutter_a_steps array and the current shutter speed
            shutter_a_steps = cinepi_controller.calculate_dynamic_shutter_angles(int(fps))
            current_shutter_a = redis_controller.get_value(ParameterKey.SHUTTER_A.value)
            socketio.emit('shutter_a_update', {'shutter_a_steps': shutter_a_steps, 'current_shutter_a': current_shutter_a})

    @socketio.on('change_wb')
    def handle_change_wb(data):
        wb = data.get('wb')
        if wb:
            cinepi_controller.set_wb(int(wb))  # Call set_wb method
            socketio.emit('parameter_change', {'wb': wb})   

    @socketio.on('change_resolution')
    def handle_change_resolution(data):
        sensor_mode = data.get('mode')
        if sensor_mode is not None:
            cinepi_controller.set_resolution(int(sensor_mode))
            socketio.emit('resolution_change', {'sensor_mode': sensor_mode})
            # Emit the current values and steps immediately before reloading
            shutter_a_steps = cinepi_controller.calculate_dynamic_shutter_angles(
                int(float(redis_controller.get_value(ParameterKey.FPS_ACTUAL.value)))
            )
            current_shutter_a = redis_controller.get_value(ParameterKey.SHUTTER_A.value)
            current_fps = redis_controller.get_value(ParameterKey.FPS_ACTUAL.value)
            socketio.emit('shutter_a_update', {
                'shutter_a_steps': shutter_a_steps,
                'current_shutter_a': current_shutter_a
            })
            socketio.emit('fps_update', {
                'fps_steps': cinepi_controller.fps_steps_dynamic,
                'current_fps': current_fps
            })

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

    @socketio.on('reboot')
    def handle_reboot():
        logging.info('socket reboot');
        cinepi_controller.reboot()

    @socketio.on('shutdown')
    def handle_shutdown():
        cinepi_controller.safe_shutdown()

from flask_socketio import emit
import threading
from module.redis_controller import ParameterKey
from module.config_loader import as_bool

def register_events(socketio, redis_controller, cinepi_controller, simple_gui, sensor_detect):
    """Server → browser push only.

    Control moved to POST /api/v1/cmd (docs/web-api.md), so the browser now
    sends the same command lines as the CLI and serial paths and behaviour
    cannot drift between them. What is left here is the push channel: the
    initial snapshot, redis-change fan-out, and the dependent step lists.
    """

    def resolution_switching_active():
        return as_bool(
            redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value, "0")
        )

    def selected_resolution_mode():
        target_mode = redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_MODE.value)
        if resolution_switching_active() and target_mode is not None:
            return target_mode
        return redis_controller.get_value(ParameterKey.SENSOR_MODE.value)

    def emit_resolution_selection(selected_mode=None):
        socketio.emit('parameter_change', {
            'selected_resolution_mode': (
                selected_mode
                if selected_mode is not None
                else selected_resolution_mode()
            ),
            'resolution_switching': redis_controller.get_value(
                ParameterKey.RESOLUTION_SWITCHING.value,
                "0",
            ),
        })
    
    @socketio.on('connect')
    def handle_connect():
        initial_values = {
            'iso': redis_controller.get_value(ParameterKey.ISO.value),
            'shutter_a': redis_controller.get_value(ParameterKey.SHUTTER_A.value),
            'fps': redis_controller.get_value(ParameterKey.FPS_ACTUAL.value),
            'background_color': simple_gui.get_background_color(),
            'iso_steps': cinepi_controller.iso_steps,
            'shutter_a_steps': cinepi_controller.shutter_a_steps_dynamic,
            'fps_steps': cinepi_controller.fps_steps_dynamic,
            'wb_steps': cinepi_controller.wb_steps,
            'wb': redis_controller.get_value(ParameterKey.WB_USER.value) or (cinepi_controller.wb_steps[0] if cinepi_controller.wb_steps else None)
        }

        initial_values.update(simple_gui.populate_values())

        initial_values['sensor_resolutions'] = sensor_detect.get_available_resolutions()
        initial_values['current_sensor'] = sensor_detect.camera_model
        initial_values['selected_resolution_mode'] = selected_resolution_mode()
        initial_values['resolution_switching'] = redis_controller.get_value(
            ParameterKey.RESOLUTION_SWITCHING.value,
            "0",
        )

        emit('initial_values', initial_values)

    def emit_step_lists():
        """Re-publish the fps-dependent shutter-angle list and the fps list.

        Both depend on the live frame rate, so a `set fps` from any path —
        web API, CLI, serial, GPIO — has to refresh them. Driven off the
        redis keys that actually reach subscribers: RedisController._listen
        deliberately does not emit for fps_actual, so keying on that alone
        would never fire.
        """
        try:
            fps_now = int(float(redis_controller.get_value(ParameterKey.FPS_ACTUAL.value)))
        except (TypeError, ValueError):
            return
        current_shutter_a = redis_controller.get_value(ParameterKey.SHUTTER_A.value)
        socketio.emit('shutter_a_update', {
            'shutter_a_steps': cinepi_controller.calculate_dynamic_shutter_angles(fps_now),
            'current_shutter_a': current_shutter_a,
        })
        socketio.emit('fps_update', {
            'fps_steps': cinepi_controller.fps_steps_dynamic,
            'fps_actual': redis_controller.get_value(ParameterKey.FPS_ACTUAL.value),
        })

    def redis_change_handler(data):
        key = data['key']
        value = data['value']
        if key in [ParameterKey.ISO.value, ParameterKey.SHUTTER_A.value, ParameterKey.FPS_ACTUAL.value, ParameterKey.WB.value, ParameterKey.FRAMECOUNT.value, ParameterKey.BUFFER.value]:
            socketio.emit('parameter_change', {key: value})

        if key == ParameterKey.WB_USER.value:
            socketio.emit('parameter_change', {'wb': value})

        if key in (ParameterKey.FPS.value,
                   ParameterKey.FPS_USER.value,
                   ParameterKey.FPS_ACTUAL.value):
            emit_step_lists()

        if key == ParameterKey.RESOLUTION_TARGET_MODE.value:
            emit_resolution_selection(value)

        if key in (ParameterKey.SENSOR_MODE.value, ParameterKey.RESOLUTION_SWITCHING.value):
            emit_resolution_selection()

        if key == ParameterKey.WB.value:
            # Defer, do not sleep. This handler runs on RedisController's single
            # _listen thread, synchronously, ahead of eight other subscribers --
            # sleeping here stalled the entire live-state bus for two seconds on
            # every white-balance change, and blocked the pub/sub loop from
            # consuming the next message at all. Same threading.Timer shape the
            # settings editor uses to let a response land before it acts.
            timer = threading.Timer(
                2.0, lambda: socketio.emit('reload_browser')
            )
            timer.daemon = True
            timer.start()

    redis_controller.redis_parameter_changed.subscribe(redis_change_handler)

    @socketio.on('update_background_color')
    def handle_update_background_color():
        background_color = simple_gui.get_background_color()
        socketio.emit('background_color_change', {'background_color': background_color})

    # No control handlers here. The browser posts command lines to
    # /api/v1/cmd, so `set iso`, `set fps`, `set resolution`, `set log`,
    # `rec` and `unmount` take exactly the path the CLI and serial take.
    # The resulting redis writes come back through redis_change_handler
    # above, and cinepi_controller's own resolution-change callback (see
    # module.app.create_app) emits `reload_stream`.

from flask import Blueprint, current_app, jsonify, request, render_template

main_routes = Blueprint('main', __name__)

@main_routes.route('/')
def index():
    redis_controller = current_app.config['REDIS_CONTROLLER']
    cinepi_controller = current_app.config['CINEPI_CONTROLLER']
    simple_gui = current_app.config['SIMPLE_GUI']
    sensor_detect = current_app.config['SENSOR_DETECT']

    iso_value = redis_controller.get_value("iso")
    shutter_a_value = redis_controller.get_value("shutter_a")
    fps_value = redis_controller.get_value("fps_actual")
    background_color_value = simple_gui.get_background_color()
    
    dynamic_data = simple_gui.populate_values()

    dynamic_data = {
        "iso": iso_value if iso_value else "Initializing...",
        "shutter_a": shutter_a_value if shutter_a_value else "Initializing...",
        "fps": fps_value if fps_value else "Initializing...",
        "background_color": background_color_value if background_color_value else "Initializing...",
    }

    return render_template('template.html', stream_url="http://cinepi.local:8000/stream", 
                           dynamic_data=dynamic_data,
                           iso_values=cinepi_controller.iso_steps, 
                           shutter_speed_values=cinepi_controller.shutter_a_steps_dynamic,
                           fps_values=cinepi_controller.fps_steps_dynamic, 
                           background_color=background_color_value)
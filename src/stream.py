import logging
from app import create_app

def run_app(host='0.0.0.0', port=5000):
    from module.cinepi_controller import CinePiController
    from module.redis_controller import RedisController
    from module.simple_gui import SimpleGUI

    redis_controller = RedisController()
    cinepi_controller = CinePiController()
    simple_gui = SimpleGUI()

    app, socketio = create_app(redis_controller, cinepi_controller, simple_gui)
    
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    socketio.run(app, host=host, port=port)

if __name__ == '__main__':
    run_app()

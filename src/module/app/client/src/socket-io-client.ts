import { io, Socket } from 'socket.io-client';

export enum CinemateSocketEmitEvents {
    CHANGE_ISO = 'change_iso',
    CHANGE_SHUTTER_A = 'change_shutter_a',
    CHANGE_FPS = 'change_fps',
    CHANGE_WB = 'change_wb',
    CHANGE_RESOLUTION = 'change_resolution',
    REC_CLICK = 'container_tap',
    UNMOUNT = 'unmount',
    REBOOT = 'reboot',
    SHUTDOWN = 'shutdown',
}

export enum CinemateSocketDataKey {
    WB_STEPS = 'wb_steps',
    WB = 'wb',
    SHUTTER_A_STEPS = 'shutter_a_steps',
    SHUTTER_A = 'shutter_a',
    CURRENT_SHUTTER_A = 'current_shutter_a',
    FPS_STEPS = 'fps_steps',
    FPS = 'fps',
    ISO_STEPS = 'iso_steps',
    ISO = 'iso',
    SENSOR_RESOLUTIONS = 'sensor_resolutions',
    SELECTED_RESOLUTION_MODE = 'selected_resolution_mode',
    BACKGROUND_COLOR = 'background_color',
    CPU_TEMP = 'cpu_temp',
    CPU_LOAD = 'cpu_load',
    RAM_LOAD = 'ram_load',
    STORAGE_TYPE = 'storage_type',
    DISK_SPACE = 'disk_space',
}

export type CinemateSocketData = { [key: string]: any };

export class CinemateSocketClient {
    private _socket: Socket;
    private _callback: (data?: CinemateSocketData) => void;

    constructor(callback: (data?: CinemateSocketData) => void) {
        this._callback = callback;

        this._socket = io();
        this._socket.on('initial_values', this._handleSocketData.bind(this));
        this._socket.on('parameter_change', this._handleSocketData.bind(this));
        this._socket.on('shutter_a_update', this._handleSocketData.bind(this));
        this._socket.on('fps_update', this._handleSocketData.bind(this));
        this._socket.on('gui_data_change', this._handleSocketData.bind(this));
        this._socket.on('background_color_change', this._handleSocketData.bind(this));

        this._socket.on('reload_browser', () => {
            window.location.reload();
        });

        //this._addSocketListeners();
    }

    private _handleSocketData(data?: CinemateSocketData) {
        //console.log('Socket data received:', data);
        this._callback(data);
    }

    private _addSocketListeners() {
        this._socket.on('initial_values', (data) => {
            /* 

            document.getElementById('framecount').innerText = data.framecount;
            document.getElementById('buffer').innerText = data.buffer;

            document.getElementById('current-sensor').innerText = data.current_sensor;
            */
        });

        this._socket.on('reload_stream', () => {
            //reloadStream();
        });
    }

    public emitChange(name: CinemateSocketEmitEvents, value?: any): void {
        console.log('emitChange', name, value);
        if (value) {
            this._socket.emit(name, value);
        } else {
            this._socket.emit(name);
        }
    }
}

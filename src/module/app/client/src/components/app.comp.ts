import {
    CinemateSocketClient,
    CinemateSocketData,
    CinemateSocketDataKey,
    CinemateSocketEmitEvents,
} from '../socket-io-client.js';
import './select.comp.js';
import './video/video.comp.js';
import './menu.comp.js';
import './info.comp.js';
import './rec-button.comp.js';
import './settings.comp.js';
import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement } from 'lit/decorators.js';
import { Options } from './select.comp.js';
import { RecStatus } from './rec-button.comp.js';
import { MenuOption, MenuOptions } from './menu.comp.js';
import { Color, IconUrl } from './app.const.js';
import { CinemateVideo, VideoOverlay } from './video/video.comp.js';
import { prefixZero, toKebabCase } from '../utils.js';

@customElement('cinemate-app')
export class CinemateApp extends LitElement {
    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            height: 100vh;
            max-height: 100vh;
        }
        .top-bar,
        .bottom-bar {
            background-color: black;
            padding: 4px 8px;
            display: flex;
            justify-content: space-between;
            flex: 0 0 auto;
            flex-wrap: wrap;
            align-items: center;
        }
        .left-container,
        .right-container {
            flex: 1;
            display: flex;
            gap: 1rem;
            justify-content: space-evenly;
        }
        .left-container {
            justify-content: flex-start;
        }
        .right-container {
            justify-content: flex-end;
        }
        .fs-button {
            border: none;
            appearance: none;
            cursor: pointer;
            padding: 0;
            display: inline-block;
            width: 16px;
            height: 16px;
            background-color: var(--color-light);
            -webkit-mask-image: var(--icon-fullscreen);
            mask-image: var(--icon-fullscreen);
            -webkit-mask-repeat: no-repeat;
            mask-repeat: no-repeat;
            -webkit-mask-size: 100% 100%;
            mask-size: 100% 100%;
        }
    `;

    private _mainMenuOptions: MenuOptions = [
        {
            label: 'Reboot',
            value: CinemateSocketEmitEvents.REBOOT,
        },
        {
            label: 'Shutdown',
            value: CinemateSocketEmitEvents.SHUTDOWN,
        },
        {
            label: 'Unmount',
            value: CinemateSocketEmitEvents.UNMOUNT,
        },
    ];

    private _overlayMenuOptions: MenuOptions = [
        {
            label: 'Zebra Stripes',
            value: VideoOverlay.Exposure,
            isToggle: true,
        },
        {
            label: 'Peaking',
            value: VideoOverlay.FocusPeaking,
            isToggle: true,
        },
        {
            label: 'Histogram',
            value: VideoOverlay.Histogram,
            isToggle: true,
        },
        {
            label: 'Vectorscope',
            value: VideoOverlay.Vectorscope,
            isToggle: true,
        },
        {
            label: 'Waveform',
            subLabel: 'Experimental',
            value: VideoOverlay.Waveform,
            isToggle: true,
        },
        {
            label: 'El Zones',
            subLabel: 'Experimental',
            value: VideoOverlay.ElColor,
            isToggle: true,
        },
        {
            label: 'False Color',
            subLabel: 'Experimental',
            value: VideoOverlay.FalseColor,
            isToggle: true,
        },
    ];

    private _socket: CinemateSocketClient;

    private _data: Map<string, any> = new Map<string, any>();

    private _shutterOptions: Options = [];
    private _selectedShutter: string = '';

    private _fpsOptions: Options = [];
    private _selectedFps: string = '';

    private _wbOptions: Options = [];
    private _selectedWb: string = '';

    private _isoOptions: Options = [];
    private _selectedIso: string = '';

    private _resolutionOptions: Options = [];
    private _selectedResolution: string = '';

    private _recStatus: RecStatus = RecStatus.Standby;

    constructor() {
        super();
        this._socket = new CinemateSocketClient(this._onSocketData.bind(this));
    }

    protected firstUpdated(_changedProperties: PropertyValues): void {
        super.firstUpdated(_changedProperties);
        this._setColorCssProperties();
        this._setIconCssProperties();
    }

    private _setIconCssProperties(): void {
        Object.keys(IconUrl).forEach((iconKey: string) => {
            this.style.setProperty(`--icon-${toKebabCase(iconKey)}`, IconUrl[iconKey as keyof typeof IconUrl]);
        });
    }

    private _setColorCssProperties(): void {
        Object.keys(Color).forEach((colorKey: string) => {
            this.style.setProperty(`--color-${toKebabCase(colorKey)}`, Color[colorKey as keyof typeof Color]);
        });
    }

    private _onSocketData(data?: CinemateSocketData) {
        const oldData = new Map(this._data);
        for (const key in data) {
            if (data.hasOwnProperty(key)) {
                this._data.set(key, data[key]);
            }
        }

        // ShutterOptions and selectedShutter do not always match same values as Oled on camera, I guess this is a bug in the backend.
        // Sometimes the selectedShutter is not part of the shutterOptions.
        this._shutterOptions = this._convertToMenuOptions(this._data.get(CinemateSocketDataKey.SHUTTER_A_STEPS));
        this._selectedShutter = (
            this._data.get(CinemateSocketDataKey.CURRENT_SHUTTER_A) ||
            this._data.get(CinemateSocketDataKey.SHUTTER_A || '')
        ).replace('.0', '');

        this._fpsOptions = this._convertToMenuOptions(this._data.get(CinemateSocketDataKey.FPS_STEPS));
        this._selectedFps = this._data.get(CinemateSocketDataKey.FPS) || '';

        this._wbOptions = this._convertToMenuOptions(this._data.get(CinemateSocketDataKey.WB_STEPS));
        this._selectedWb = this._data.get(CinemateSocketDataKey.WB) || '';

        this._isoOptions = this._convertToMenuOptions(this._data.get(CinemateSocketDataKey.ISO_STEPS));
        this._selectedIso = this._data.get(CinemateSocketDataKey.ISO) || '';

        this._resolutionOptions =
            this._data.get(CinemateSocketDataKey.SENSOR_RESOLUTIONS)?.map((res: any) => ({
                value: res.mode,
                label: res.resolution,
            })) || [];
        this._selectedResolution = this._data.get(CinemateSocketDataKey.SELECTED_RESOLUTION_MODE) || '';

        //Not ideal to map to colors would be better to just get a status from backend
        this._recStatus = this._data.get(CinemateSocketDataKey.BACKGROUND_COLOR) || RecStatus.Standby;

        if (oldData !== this._data) {
            this.requestUpdate();
        }
    }

    private _convertToMenuOptions(rawOptions: string[] | undefined): Options {
        return (
            rawOptions?.map((option: any) => ({
                value: option,
            })) || []
        );
    }

    private _onIsoSelect(event: CustomEvent) {
        console.log('iso changed requested:', event);
        this._socket.emitChange(CinemateSocketEmitEvents.CHANGE_ISO, { iso: event.detail.value });
    }

    private _onShutterSelect(event: CustomEvent) {
        console.log('shutter changed requested:', event);
        this._socket.emitChange(CinemateSocketEmitEvents.CHANGE_SHUTTER_A, { shutter_a: event.detail.value });
    }

    private _onFpsSelect(event: CustomEvent) {
        console.log('fps changed requested:', event);
        this._socket.emitChange(CinemateSocketEmitEvents.CHANGE_FPS, { fps: event.detail.value });
    }

    private _onWbSelect(event: CustomEvent) {
        console.log('wb changed requested:', event);
        this._socket.emitChange(CinemateSocketEmitEvents.CHANGE_WB, { wb: event.detail.value });
    }

    private _onResolutionSelect(event: CustomEvent) {
        console.log('resolution changed requested:', event);
        this._socket.emitChange(CinemateSocketEmitEvents.CHANGE_RESOLUTION, { mode: event.detail.value });
    }

    private _onRecClick() {
        console.log('rec clicked');
        this._socket.emitChange(CinemateSocketEmitEvents.REC_CLICK);
    }

    private _onFullScreenClick() {
        const elem = document.documentElement;
        if (!document.fullscreenElement) {
            if (elem.requestFullscreen) {
                elem.requestFullscreen();
            } else if ((elem as any).webkitRequestFullscreen) {
                (elem as any).webkitRequestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if ((document as any).webkitExitFullscreen) {
                (document as any).webkitExitFullscreen();
            }
        }
    }

    private _onMainMenuclick(e: CustomEvent): void {
        console.log('_onMainMenuclick', e.detail);
        const option = e.detail as MenuOption;
        if (option.isToggle) {
            option.isToggled = !option.isToggled;
        }
        this._mainMenuOptions = this._mainMenuOptions.map((opt) =>
            opt.value === option.value ? { ...opt, ...option } : opt
        );
        this._socket.emitChange(option.value as CinemateSocketEmitEvents);
        this.requestUpdate();
    }

    private _onOverlayMenuclick(e: CustomEvent): void {
        console.log('_onOverlayMenuclick', e.detail);
        const option = e.detail as MenuOption;
        if (option.isToggle) {
            option.isToggled = !option.isToggled;
        }
        this._overlayMenuOptions = this._overlayMenuOptions.map((opt) =>
            opt.value === option.value ? { ...opt, ...option } : opt
        );

        const activeOverlays = this._overlayMenuOptions
            .map((option) => (option.isToggled ? option.value : ''))
            .filter(Boolean);

        (this.renderRoot.querySelector('cinemate-video') as CinemateVideo).activeOverlays = activeOverlays;
        this.requestUpdate();
    }

    render() {
        return html`
            <div class="top-bar">
                <cinemate-menu
                    @option-clicked="${this._onMainMenuclick}"
                    .options="${this._mainMenuOptions}"
                ></cinemate-menu>
                <button @click="${this._onFullScreenClick}" class="fs-button"></button>
                <cinemate-select
                    .options=${this._fpsOptions}
                    selected="${this._selectedFps}"
                    label="FPS"
                    @change=${this._onFpsSelect}
                ></cinemate-select>
                <cinemate-select
                    .options=${this._shutterOptions}
                    selected="${this._selectedShutter}"
                    label="SHUTTER"
                    suffix="°"
                    @change=${this._onShutterSelect}
                ></cinemate-select>
                <cinemate-select
                    .options=${this._isoOptions}
                    selected="${this._selectedIso}"
                    label="ISO"
                    @change=${this._onIsoSelect}
                ></cinemate-select>
                <cinemate-select
                    .options=${this._wbOptions}
                    selected="${this._selectedWb}"
                    label="WB"
                    suffix="K"
                    @change=${this._onWbSelect}
                ></cinemate-select>
                <cinemate-select
                    .options=${this._resolutionOptions}
                    selected="${this._selectedResolution}"
                    label="RES."
                    @change=${this._onResolutionSelect}
                ></cinemate-select>
                <!-- implement framecount/time when it's correct from backend -->
                <!--${this._recStatus !== 'black'
                    ? html`<p class="stats">FC: ${this._data.get('frame_count')}</p>`
                    : null}-->
            </div>
            <!-- <cinemate-video src="http://cinepi.local:8000/stream"></cinemate-video> -->
            <!-- <cinemate-video src="../static/image.png"></cinemate-video> -->
            <cinemate-video></cinemate-video>
            <div class="bottom-bar">
                <div class="left-container">
                    <cinemate-menu
                        @option-clicked="${this._onOverlayMenuclick}"
                        .options="${this._overlayMenuOptions}"
                        .icon="${IconUrl.Overlay}"
                    ></cinemate-menu>
                    <cinemate-settings></cinemate-settings>
                    <cinemate-info
                        label="MEDIA"
                        value="${this._data.get(CinemateSocketDataKey.DISK_SPACE)}"
                    ></cinemate-info>
                </div>
                <cinemate-rec-button .status="${this._recStatus}" @click="${this._onRecClick}"></cinemate-rec-button>
                <div class="right-container">
                    <cinemate-info
                        label="CPU"
                        value="${prefixZero(this._data.get(CinemateSocketDataKey.CPU_LOAD))} ${prefixZero(
                            this._data.get(CinemateSocketDataKey.CPU_TEMP)
                        )}"
                    ></cinemate-info>
                    <cinemate-info
                        label="RAM"
                        value="${prefixZero(this._data.get(CinemateSocketDataKey.RAM_LOAD))}"
                    ></cinemate-info>
                </div>
            </div>
        `;
    }
}

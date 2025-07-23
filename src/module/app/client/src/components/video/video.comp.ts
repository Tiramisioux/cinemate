import { html, css, LitElement } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { Histogram } from './overlays/histogram.overlay';
import { FocusPeaking } from './overlays/focus-peaking.overlay';
import { Exposure } from './overlays/exposure.overlay';
import { Waveform } from './overlays/waveform.overlay';
import { Vectorscope } from './overlays/vectorscope.overlay';
import { OverlayBase } from './overlays/overlay-base';
import { EL_ZONE_COLORS, ElColor } from './overlays/el-color.overlay';
import { FalseColor, falseColorLut } from './overlays/false-color.overlay';

export enum VideoOverlay {
    Vectorscope = 'vectorscope',
    Histogram = 'histogram',
    Exposure = 'exposure',
    FocusPeaking = 'focus-peaking',
    Waveform = 'waveform',
    ElColor = 'el-color',
    FalseColor = 'false-color',
}

@customElement('cinemate-video')
export class CinemateVideo extends LitElement {
    static styles = css`
        :host {
            position: relative;
            flex: 1 1 auto;
            min-height: 0;
            min-width: 0;
            display: block;
            background: black;
            overflow: hidden;
        }
        #video-stream {
            position: relative;
            width: auto;
            height: 100%;
            display: block;
            margin-left: auto;
            margin-right: auto;
        }
        @media (orientation: portrait) {
            #video-stream {
                width: 100%;
                height: auto;
                top: 50%;
                transform: translateY(-50%);
            }
        }
        #focus-canvas,
        #exposure-canvas,
        #false-canvas,
        #el-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        #histogram-canvas {
            position: absolute;
            bottom: 8px;
            right: 8px;
        }
        #waveform-canvas {
            position: absolute;
            bottom: 8px;
            right: 8px;
        }
        #vectorscope-canvas {
            position: absolute;
            bottom: 8px;
            right: 8px;
        }
        .el-zones-bar,
        .false-color-bar {
            display: var(--el-zones-display, none);
            position: absolute;
            top: 0;
            height: calc(100vh - var(--top-bar-height) - var(--bottom-bar-height));
            background: var(--color-dark-transparent);
            color: var(--color-light);
            right: 0;
            flex-flow: column;
            z-index: 1;
        }
        .false-color-bar {
            display: var(--false-color-display, none);
        }
        .el-zone,
        .false-color {
            flex: 1 1 auto;
            display: flex;
            justify-content: flex-end;
            gap: 0.5rem;
        }
        .el-zone-color,
        .false-color-color {
            display: inline-block;
            width: 20px;
            height: 100%;
        }
        .status-overlay {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 100%;
            height: 100%;
            transform: translate(-50%, -50%);
            border: 2px solid var(--status-color);
        }
    `;

    @property({ type: String })
    src: string = 'https://picsum.photos/2028/1520';

    @property({ type: Array })
    activeOverlays: string[] = [];

    private _animationFrame: number | null = null;

    private _histogram: Histogram | undefined;
    private _focusPeaking: FocusPeaking | undefined;
    private _exposure: Exposure | undefined;
    private _waveform: Waveform | undefined;
    private _vectorScope: Vectorscope | undefined;
    private _el: ElColor | undefined;
    private _falseColor: FalseColor | undefined;
    private _overlays: OverlayBase[] = [];

    firstUpdated() {

        this._exposure = new Exposure(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#exposure-canvas') as HTMLCanvasElement
        );
        this._el = new ElColor(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#el-canvas') as HTMLCanvasElement
        );
        this._falseColor = new FalseColor(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#false-canvas') as HTMLCanvasElement,
        );
        this._focusPeaking = new FocusPeaking(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#focus-canvas') as HTMLCanvasElement
        );
        this._histogram = new Histogram(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#histogram-canvas') as HTMLCanvasElement
        );
        this._vectorScope = new Vectorscope(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#vectorscope-canvas') as HTMLCanvasElement
        );
        this._waveform = new Waveform(
            this._img as HTMLImageElement,
            this.renderRoot.querySelector('#waveform-canvas') as HTMLCanvasElement
        );
        this._overlays = [
            this._exposure,
            this._focusPeaking,
            this._histogram,
            this._vectorScope,
            this._waveform,
            this._el,
            this._falseColor,
        ];
        this._toggleOverlays();
        this._updateOverlays();
    }

    updated(changedProps: Map<string, any>) {
        if (changedProps.has('activeOverlays')) {
            this._toggleOverlays();
        }
    }

    private get _img(): HTMLImageElement | null {
        return this.renderRoot.querySelector('#video-stream') as HTMLImageElement;
    }

    private _toggleOverlays() {
        this._overlays.forEach((overlay) => {
            overlay.enabled = this.activeOverlays.includes(overlay.name);
            if (overlay.name === VideoOverlay.ElColor) {
                this.style.setProperty('--el-zones-display', overlay.enabled ? 'flex' : 'none');
            }
            if (overlay.name === VideoOverlay.FalseColor) {
                this.style.setProperty('--false-color-display', overlay.enabled ? 'flex' : 'none');
            }
        });
    }

    private _updateOverlays() {
        if (!this._img) return;
        
        const statusOverlay = this.renderRoot.querySelector('.status-overlay') as HTMLDivElement;
        if (statusOverlay) {
            statusOverlay.style.width = (this._img.getBoundingClientRect().width - 4) + 'px';
            statusOverlay.style.height = (this._img.getBoundingClientRect().height - 4) + 'px';
        }

        this._overlays.forEach((overlay) => overlay.update());
        this._animationFrame = requestAnimationFrame(() => this._updateOverlays());
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._animationFrame) {
            cancelAnimationFrame(this._animationFrame);
        }
    }

    render() {
        return html`
            <img id="video-stream" src="${this.src}" crossorigin="anonymous"/>
            <div class="el-zones-bar">
                ${Object.keys(EL_ZONE_COLORS)
                    .sort((a, b) => parseFloat(a) - parseFloat(b))
                    .map((zone: any) => {
                        const color = `rgb(${EL_ZONE_COLORS[zone][0]}, ${EL_ZONE_COLORS[zone][1]}, ${EL_ZONE_COLORS[zone][2]})`;
                        return html`
                            <div class="el-zone">
                                <span class="el-zone-label">${zone}</span>
                                <span class="el-zone-color" style="background: ${color};"></span>
                            </div>
                        `;
                    })}
            </div>
            <div class="false-color-bar">
                ${falseColorLut.map((colorSpan: any) => {
                    const color = `rgb(${colorSpan.color[0]}, ${colorSpan.color[1]}, ${colorSpan.color[2]})`;
                    return html`
                        <div class="false-color">
                            <span class="false-color-label">${colorSpan.label}</span>
                            <span class="false-color-color" style="background: ${color};"></span>
                        </div>
                    `;
                })}
            </div>
            <div class="status-overlay"></div>
            <canvas id="focus-canvas"></canvas>
            <canvas id="exposure-canvas"></canvas>
            <canvas id="el-canvas"></canvas>
            <canvas id="false-canvas"></canvas>
            <canvas id="histogram-canvas"></canvas>
            <canvas id="waveform-canvas"></canvas>
            <canvas id="vectorscope-canvas"></canvas>
        `;
    }
}

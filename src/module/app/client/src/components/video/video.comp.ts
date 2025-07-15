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
        }
        img,
        #main-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            background-color: black;
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
    `;

    @property({ type: String })
    src: string = 'https://picsum.photos/915/354';

    @property({ type: Array })
    activeOverlays: string[] = [];

    private _lastDrawTime = 0;
    private _previewUpDateRateFPS = 25;

    private _img: HTMLImageElement | null = null;
    private _animationFrame: number | null = null;

    private _mainCanvas: HTMLCanvasElement | undefined;
    private _ctx: CanvasRenderingContext2D | null | undefined;

    private _histogram: Histogram | undefined;
    private _focusPeaking: FocusPeaking | undefined;
    private _exposure: Exposure | undefined;
    private _waveform: Waveform | undefined;
    private _vectorScope: Vectorscope | undefined;
    private _el: ElColor | undefined;
    private _falseColor: FalseColor | undefined;
    private _overlays: OverlayBase[] = [];

    firstUpdated() {
        this._mainCanvas = this.renderRoot.querySelector('#main-canvas') as HTMLCanvasElement;
        this._ctx = this._mainCanvas.getContext('2d', { willReadFrequently: true, alpha: false });
        this._img = new window.Image();
        this._img.crossOrigin = 'anonymous';
        this._img.onload = () => this._drawFrame();

        this._exposure = new Exposure(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#exposure-canvas') as HTMLCanvasElement
        );
        this._el = new ElColor(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#el-canvas') as HTMLCanvasElement
        );
        this._falseColor = new FalseColor(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#false-canvas') as HTMLCanvasElement
        );
        this._focusPeaking = new FocusPeaking(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#focus-canvas') as HTMLCanvasElement
        );
        this._histogram = new Histogram(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#histogram-canvas') as HTMLCanvasElement
        );
        this._vectorScope = new Vectorscope(
            this._mainCanvas,
            this._ctx!,
            this.renderRoot.querySelector('#vectorscope-canvas') as HTMLCanvasElement
        );
        this._waveform = new Waveform(
            this._mainCanvas,
            this._ctx!,
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
        this._startStream();
    }

    updated(changedProps: Map<string, any>) {
        if (changedProps.has('activeOverlays')) {
            this._toggleOverlays();
        }
        if (changedProps.has('src')) {
            this._startStream();
        }
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

    private _startStream() {
        if (!this._img) return;
        // For MJPEG, set the src to the stream URL
        this._img.crossOrigin = 'anonymous';
        this._img.src = this.src;
    }

    private _drawFrame() {
        // only update at max at the framerate that _previewUpDateRateFPS is set to.
        const now = performance.now();
        const minInterval = 1000 / this._previewUpDateRateFPS;
        if (now - this._lastDrawTime < minInterval) {
            this._animationFrame = requestAnimationFrame(() => this._drawFrame());
            return;
        }
        this._lastDrawTime = now;

        if (!this._mainCanvas || !this._img || !this._ctx) return;

        // Resize canvas to match image
        if (this._mainCanvas.width !== this._img.naturalWidth) {
            this._mainCanvas.width = this._img.naturalWidth;
            this._mainCanvas.height = this._img.naturalHeight;
        }
        this._ctx.drawImage(this._img, 0, 0, this._mainCanvas.width, this._mainCanvas.height);

        this._overlays.forEach((overlay) => overlay.update());
        this._animationFrame = requestAnimationFrame(() => this._drawFrame());
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._animationFrame) {
            cancelAnimationFrame(this._animationFrame);
        }
    }

    render() {
        return html`
            <canvas id="main-canvas"></canvas>
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
            <canvas id="focus-canvas"></canvas>
            <canvas id="exposure-canvas"></canvas>
            <canvas id="el-canvas"></canvas>
            <canvas id="false-canvas"></canvas>
            <canvas id="histogram-canvas"></canvas>
            <canvas id="waveform-canvas"></canvas>
            <canvas id="vectorscope-canvas"></canvas>
        `;
    }

    /* render() {
        return html`<img src="${this.src}" />`;
    } */
}

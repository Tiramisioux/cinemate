import { Color } from '../../app.const';
import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

export class Histogram extends OverlayBase {
    private _histogramCanvas: HTMLCanvasElement;
    private _histogramContext: CanvasRenderingContext2D | null;
    private _width: number = 200;
    private _height: number = 100;
    private _x: number = 0;
    private _y: number = 0;

    constructor(
        videoCanvas: HTMLCanvasElement,
        videoContext: CanvasRenderingContext2D,
        histogramCanvas: HTMLCanvasElement
    ) {
        super(videoCanvas, videoContext);
        this.name = VideoOverlay.Histogram;
        this.upDateRateFPS = 10;

        this._histogramCanvas = histogramCanvas;
        if (this._histogramCanvas) {
            this._histogramCanvas.width = this._width;
            this._histogramCanvas.height = this._height;
        }
        this._histogramContext = this._histogramCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this._histogramContext) {
            return;
        }

        const data = this.videoContext?.getImageData(0, 0, this.videoCanvas.width, this.videoCanvas.height).data || [];
        const hist = new Array(256).fill(0);
        // Calculate luminance histogram
        for (let i = 0; i < data.length; i += 4) {
            const r = this.limiteRgbToFullRGB(data[i]);
            const g = this.limiteRgbToFullRGB(data[i + 1]);
            const b = this.limiteRgbToFullRGB(data[i + 2]);
            // Standard luminance formula
            const lum = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
            hist[lum]++;
        }

        // Find max value for scaling
        const max = Math.max(...hist) || 1;

        // Draw semi-transparent background
        this._histogramContext.clearRect(0, 0, this._width, this._height);
        this._histogramContext.fillStyle = Color.DarkTransparent;
        this._histogramContext.fillRect(this._x, this._y, this._width, this._height);

        const binWidth = this._width / hist.length;
        for (let bin = 0; bin < hist.length; bin++) {
            const h = Math.round((hist[bin] / max) * (this._height - 2));
            this._histogramContext.fillStyle = Color.Light;
            this._histogramContext.fillRect(this._x + bin * binWidth, this._y + this._height - 1 - h, binWidth, h);
        }
    }

    public clear(): void {
        this._histogramContext?.clearRect(0, 0, this._width, this._height);
    }
}

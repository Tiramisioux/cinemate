import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

export class Waveform extends OverlayBase {
    private _waveformCanvas: HTMLCanvasElement;
    private _waveformContext: CanvasRenderingContext2D | null;

    private _width: number = 200;
    private _height: number = 100;
    private _x: number = 0;
    private _y: number = 0;

    constructor(
        videoCanvas: HTMLCanvasElement,
        videoContext: CanvasRenderingContext2D,
        waveformCanvas: HTMLCanvasElement
    ) {
        super(videoCanvas, videoContext);
        this.name = VideoOverlay.Waveform;
        this.upDateRateFPS = 10;

        this._waveformCanvas = waveformCanvas;
        if (this._waveformCanvas) {
            this._waveformCanvas.width = this._width;
            this._waveformCanvas.height = this._height;
        }
        this._waveformContext = this._waveformCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this._waveformContext) {
            return;
        }

        const data = this.videoContext?.getImageData(0, 0, this.videoCanvas.width, this.videoCanvas.height).data || [];

        this._waveformContext.clearRect(0, 0, this._width, this._height);

        for (let x = 0; x < this._width; x++) {
            for (let y = 0; y < this._height; y++) {
                const idx = (y * this._width + x) * 4;
                const r = this.limiteRgbToFullRGB(data[idx]);
                const g = this.limiteRgbToFullRGB(data[idx + 1]);
                const b = this.limiteRgbToFullRGB(data[idx + 2]);

                // Plot R
                const rY = this._height - Math.round((r / 255) * this._height);
                this._waveformContext.fillStyle = 'rgba(255,0,0,0.7)';
                this._waveformContext.fillRect(x, rY, 1, 1);

                // Plot G
                const gY = this._height - Math.round((g / 255) * this._height);
                this._waveformContext.fillStyle = 'rgba(0,255,0,0.7)';
                this._waveformContext.fillRect(x, gY, 1, 1);

                // Plot B
                const bY = this._height - Math.round((b / 255) * this._height);
                this._waveformContext.fillStyle = 'rgba(0,0,255,0.7)';
                this._waveformContext.fillRect(x, bY, 1, 1);
            }
        }
    }

    public clear(): void {
        this._waveformContext?.clearRect(0, 0, this._width, this._height);
    }
}

import { CinemateSettings, SettingsKey } from '../../settings.comp';
import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

// LUT bands based on your image (IRE % mapped to 8bit luma 0–255)
export const falseColorLut = [
    { min: 0, max: 16, color: [48, 16, 64], label: '-10%' }, // -10% Purple
    { min: 16, max: 32, color: [0, 48, 128], label: '0%' }, // 0% Blue
    { min: 32, max: 48, color: [0, 96, 160], label: '10%' }, // 10% Blue-Teal
    { min: 48, max: 64, color: [32, 128, 160], label: '20%' }, // 20% Teal
    { min: 64, max: 80, color: [64, 160, 128], label: '30%' }, // 30% Gray-Green
    { min: 80, max: 96, color: [64, 192, 64], label: '40%' }, // 40% Green
    { min: 96, max: 112, color: [128, 128, 128], label: '50%' }, // 50% Gray
    { min: 112, max: 128, color: [192, 96, 96], label: '60%' }, // 60% Salmon
    { min: 128, max: 144, color: [192, 192, 192], label: '70%' }, // 70% Light Gray
    { min: 144, max: 160, color: [255, 255, 0], label: '80%' }, // 80% Yellow
    { min: 160, max: 176, color: [255, 192, 0], label: '90%' }, // 90% Orange
    { min: 176, max: 192, color: [255, 128, 0], label: '100%' }, // 100% Deep Orange
    { min: 192, max: 255, color: [255, 0, 0], label: '110%' }, // 110% Red
];

export class FalseColor extends OverlayBase {
    // Downscale factor for performance
    private _scale: number = 0.3; // Adjust for quality/performance tradeoff

    private _falseColorCanvas: HTMLCanvasElement;
    private _falseColorContext: CanvasRenderingContext2D | null;

    constructor(
        imageElement: HTMLImageElement,
        falseColorCanvas: HTMLCanvasElement,
    ) {
        super(imageElement);
        this.name = VideoOverlay.FalseColor;

        this._falseColorCanvas = falseColorCanvas;
        this._falseColorContext = this._falseColorCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this.tempCtx || !this._falseColorContext) {
            return;
        }

        this._falseColorCanvas.width = this.imageElement.naturalWidth;
        this._falseColorCanvas.height = this.imageElement.naturalHeight;

        this.tempCanvas.width = Math.max(1, Math.floor(this._falseColorCanvas.width * this._scale));
        this.tempCanvas.height = Math.max(1, Math.floor(this._falseColorCanvas.height * this._scale));
        this.tempCtx.drawImage(this.imageElement, 0, 0, this.tempCanvas.width, this.tempCanvas.height);

        // Get image data from the downscaled canvas
        const imageData = this.tempCtx.getImageData(0, 0, this.tempCanvas.width, this.tempCanvas.height);
        const { data, width, height } = imageData;

        function getFalseColor(luma: number): [number, number, number] | number[] {
            for (const band of falseColorLut) {
                if (luma >= band.min && luma < band.max) {
                    return band.color;
                }
            }
            return falseColorLut[falseColorLut.length - 1].color; // fallback
        }

        // === Process each pixel ===
        for (let i = 0; i < data.length; i += 4) {
            const r = this.limitedRgbToFullRGB(data[i]);
            const g = this.limitedRgbToFullRGB(data[i + 1]);
            const b = this.limitedRgbToFullRGB(data[i + 2]);
            const luma = 0.299 * r + 0.587 * g + 0.114 * b;

            const [fr, fg, fb] = getFalseColor(luma);
            data[i] = fr;
            data[i + 1] = fg;
            data[i + 2] = fb;
            // data[i + 3] = 180; // optional
        }

        // Put processed data back to the temp canvas
        this.tempCtx.putImageData(new ImageData(data, width, height), 0, 0);

        // Draw the processed (upscaled) result back onto the main canvas
        this._falseColorContext.drawImage(this.tempCanvas, 0, 0, this._falseColorCanvas.width, this._falseColorCanvas.height);
    }

    public clear(): void {
        this._falseColorContext?.clearRect(0, 0, this._falseColorCanvas.width, this._falseColorCanvas.height);
    }
}

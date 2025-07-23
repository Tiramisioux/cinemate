import { CinemateSettings, SettingsKey } from '../../settings.comp';
import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

export class FocusPeaking extends OverlayBase {
    // Downscale factor for performance
    private _scale: number = 0.5; // Adjust for quality/performance tradeoff

    private _focusCanvas: HTMLCanvasElement;
    private _focusContext: CanvasRenderingContext2D | null;
    private _threshold: number = FocusPeaking.DefaultThreshold;

    public static readonly MinThreshold: number = 0;
    public static readonly MaxThreshold: number = 255;
    public static readonly DefaultThreshold: number = 80;

    constructor(
        imageElement: HTMLImageElement,
        focusCanvas: HTMLCanvasElement
    ) {
        super(imageElement);
        this.name = VideoOverlay.FocusPeaking;

        this._focusCanvas = focusCanvas;
        this._focusContext = this._focusCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this.tempCtx || !this._focusContext) {
            return;
        }

        this._threshold = CinemateSettings.LoadSettingAsInt(
            SettingsKey.FocusPeakingThreshold,
            FocusPeaking.DefaultThreshold
        );

        this._focusCanvas.width = this.imageElement.naturalWidth;
        this._focusCanvas.height = this.imageElement.naturalHeight;

        this.tempCanvas.width = Math.max(1, Math.floor(this._focusCanvas.width * this._scale));
        this.tempCanvas.height = Math.max(1, Math.floor(this._focusCanvas.height * this._scale));
        this.tempCtx.drawImage(this.imageElement, 0, 0, this.tempCanvas.width, this.tempCanvas.height);

        // Get image data from the downscaled canvas
        const imageData = this.tempCtx.getImageData(0, 0, this.tempCanvas.width, this.tempCanvas.height);
        const { data, width, height } = imageData;
        const output = new Uint8ClampedArray(data.length);

        // Simple Sobel edge detection
        const sobelX = [-1, 0, 1, -2, 0, 2, -1, 0, 1];
        const sobelY = [-1, -2, -1, 0, 0, 0, 1, 2, 1];

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                let gx = 0,
                    gy = 0;
                for (let ky = -1; ky <= 1; ky++) {
                    for (let kx = -1; kx <= 1; kx++) {
                        const px = ((y + ky) * width + (x + kx)) * 4;
                        const gray = 0.299 * data[px] + 0.587 * data[px + 1] + 0.114 * data[px + 2];
                        const kernelIdx = (ky + 1) * 3 + (kx + 1);
                        gx += gray * sobelX[kernelIdx];
                        gy += gray * sobelY[kernelIdx];
                    }
                }
                const magnitude = Math.sqrt(gx * gx + gy * gy);
                const outIdx = (y * width + x) * 4;
                if (magnitude > this._threshold) {
                    // Edge: green, opaque
                    output[outIdx] = 0;
                    output[outIdx + 1] = 255;
                    output[outIdx + 2] = 0;
                    output[outIdx + 3] = 255;
                } else {
                    // Not edge: fully transparent
                    output[outIdx] = 0;
                    output[outIdx + 1] = 0;
                    output[outIdx + 2] = 0;
                    output[outIdx + 3] = 0;
                }
            }
        }

        // Put processed data back to the temp canvas
        this.tempCtx.putImageData(new ImageData(output, width, height), 0, 0);

        // Draw the processed (upscaled) result back onto the main canvas
        this._focusContext.drawImage(this.tempCanvas, 0, 0, this._focusCanvas.width, this._focusCanvas.height);
    }

    public clear(): void {
        this._focusContext?.clearRect(0, 0, this._focusCanvas.width, this._focusCanvas.height);
    }
}

import { CinemateSettings, SettingsKey } from '../../settings.comp';
import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

export class Exposure extends OverlayBase {
    // Downscale factor for performance
    private _scale: number = 0.5; // Adjust for quality/performance tradeoff
    private _tempCanvas: HTMLCanvasElement;
    private _tempCtx: CanvasRenderingContext2D | null;

    private _exposureCanvas: HTMLCanvasElement;
    private _exposureContext: CanvasRenderingContext2D | null;
    private _threshold: number = Exposure.DefaultThreshold;

    public static readonly MinThreshold: number = 0;
    public static readonly MaxThreshold: number = 255;
    public static readonly DefaultThreshold: number = 230;

    constructor(
        videoCanvas: HTMLCanvasElement,
        videoContext: CanvasRenderingContext2D,
        exposureCanvas: HTMLCanvasElement
    ) {
        super(videoCanvas, videoContext);
        this.name = VideoOverlay.Exposure;

        // Create a temporary canvas for downscaled processing
        this._tempCanvas = document.createElement('canvas');
        this._tempCtx = this._tempCanvas.getContext('2d', { willReadFrequently: true });

        this._exposureCanvas = exposureCanvas;
        this._exposureContext = this._exposureCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this._tempCtx || !this._exposureContext) {
            return;
        }

        this._threshold = CinemateSettings.LoadSettingAsInt(
            SettingsKey.ZebraStripesThreshold,
            Exposure.DefaultThreshold
        );

        this._exposureCanvas.width = this.videoCanvas.width;
        this._exposureCanvas.height = this.videoCanvas.height;

        this._tempCanvas.width = Math.max(1, Math.floor(this.videoCanvas.width * this._scale));
        this._tempCanvas.height = Math.max(1, Math.floor(this.videoCanvas.height * this._scale));
        this._tempCtx.drawImage(this.videoCanvas, 0, 0, this._tempCanvas.width, this._tempCanvas.height);

        // Get image data from the downscaled canvas
        const imageData = this._tempCtx.getImageData(0, 0, this._tempCanvas.width, this._tempCanvas.height);
        const { data, width, height } = imageData;
        const output = new Uint8ClampedArray(data.length);

        const stripeWidth = 4; // Width of each stripe in pixels

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const idx = (y * width + x) * 4;
                // Calculate luminance or use a channel
                const r = this.limiteRgbToFullRGB(data[idx]),
                    g = this.limiteRgbToFullRGB(data[idx + 1]),
                    b = this.limiteRgbToFullRGB(data[idx + 2]);
                const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
                if (luminance > this._threshold) {
                    // Zebra pattern: alternate stripes
                    if (((x + y) / stripeWidth) % 2 < 1) {
                        // White stripe
                        output[idx] = 255;
                        output[idx + 1] = 255;
                        output[idx + 2] = 255;
                        output[idx + 3] = 180; // semi-transparent
                    } else {
                        // Black stripe
                        output[idx] = 0;
                        output[idx + 1] = 0;
                        output[idx + 2] = 0;
                        output[idx + 3] = 180; // semi-transparent
                    }
                } else {
                    // Not overexposed: transparent
                    output[idx] = 0;
                    output[idx + 1] = 0;
                    output[idx + 2] = 0;
                    output[idx + 3] = 0;
                }
            }
        }

        // Put processed data back to the temp canvas
        this._tempCtx.putImageData(new ImageData(output, width, height), 0, 0);

        // Draw the processed (upscaled) result back onto the main canvas
        this._exposureContext.drawImage(this._tempCanvas, 0, 0, this.videoCanvas.width, this.videoCanvas.height);
    }

    public clear(): void {
        this._exposureContext?.clearRect(0, 0, this._exposureCanvas.width, this._exposureCanvas.height);
    }
}

import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

// Example EL Zone color map (customize as needed)
export const EL_ZONE_COLORS: { [zone: string]: [number, number, number] } = {
    ['-6']: [0, 0, 0],
    ['-5']: [32, 0, 64],
    ['-4']: [0, 0, 128],
    ['-3']: [0, 64, 128],
    ['-2']: [0, 128, 128],
    ['-1']: [0, 128, 64],
    ['-0.5']: [64, 128, 64],
    ['0']: [109, 109, 109], // Center (18% IRE)
    ['0.5']: [128, 192, 128],
    ['1']: [192, 255, 128],
    ['2']: [255, 255, 0],
    ['3']: [255, 192, 0],
    ['4']: [255, 128, 0],
    ['5']: [255, 64, 0],
    ['6']: [255, 255, 255],
    // Adjust colors as needed for your workflow
};

export class ElColor extends OverlayBase {
    // Downscale factor for performance
    private _scale: number = 0.3; // Adjust for quality/performance tradeoff

    private _exposureCanvas: HTMLCanvasElement;
    private _exposureContext: CanvasRenderingContext2D | null;

    constructor(
        imageElement: HTMLImageElement,
        exposureCanvas: HTMLCanvasElement
    ) {
        super(imageElement);
        this.name = VideoOverlay.ElColor;

        this._exposureCanvas = exposureCanvas;
        this._exposureContext = this._exposureCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this.tempCtx || !this._exposureContext) {
            return;
        }

        this._exposureCanvas.width = this.imageElement.naturalWidth;
        this._exposureCanvas.height = this.imageElement.naturalHeight;

        this.tempCanvas.width = Math.max(1, Math.floor(this._exposureCanvas.width * this._scale));
        this.tempCanvas.height = Math.max(1, Math.floor(this._exposureCanvas.height * this._scale));
        this.tempCtx.drawImage(this.imageElement, 0, 0, this.tempCanvas.width, this.tempCanvas.height);

        const imageData = this.tempCtx.getImageData(0, 0, this.tempCanvas.width, this.tempCanvas.height);
        const { data, width, height } = imageData;

        const zoneKeys = [];

        for (let i = 0; i < data.length; i += 4) {
            // Calculate luminance in limited range
            const yRaw = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
            // Normalize [16,235] to [0,1]
            const yNorm = Math.max(0, Math.min(1, (yRaw - 16) / (235 - 16)));
            // Map to zone range [-6, 6]
            let zoneValue = yNorm * 12 - 6;

            // Snap to half stops only between -1 and 1, else snap to full stops
            let snappedZone: number;
            if (zoneValue >= -1 && zoneValue <= 1) {
                snappedZone = Math.round(zoneValue * 2) / 2;
            } else {
                snappedZone = Math.round(zoneValue);
            }
            snappedZone = Math.max(-6, Math.min(6, snappedZone));
            const zoneKey = snappedZone % 1 === 0 ? String(snappedZone) : snappedZone.toFixed(1);
            zoneKeys.push(zoneKey);

            const color = EL_ZONE_COLORS[zoneKey] || [0, 0, 0];
            data[i] = color[0];
            data[i + 1] = color[1];
            data[i + 2] = color[2];
            // Optionally set alpha for semi-transparency
            // data[i + 3] = 180;
        }

        this.tempCtx.putImageData(new ImageData(data, width, height), 0, 0);
        this._exposureContext.drawImage(this.tempCanvas, 0, 0, this._exposureCanvas.width, this._exposureCanvas.height);
    }

    public clear(): void {
        this._exposureContext?.clearRect(0, 0, this._exposureCanvas.width, this._exposureCanvas.height);
    }
}

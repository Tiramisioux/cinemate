import { VideoOverlay } from '../video.comp';
import { OverlayBase } from './overlay-base';

export class Vectorscope extends OverlayBase {
    private _vectorScopeCanvas: HTMLCanvasElement;
    private _vectorScopeContext: CanvasRenderingContext2D | null;

    private _size: number = 256;

    constructor(
        imageElement: HTMLImageElement,
        vectorscopeCanvas: HTMLCanvasElement
    ) {
        super(imageElement);
        this.name = VideoOverlay.Vectorscope;
        this.upDateRateFPS = 10;

        this._vectorScopeCanvas = vectorscopeCanvas;
        if (this._vectorScopeCanvas) {
            this._vectorScopeCanvas.width = this._size;
            this._vectorScopeCanvas.height = this._size;
        }
        this._vectorScopeContext = this._vectorScopeCanvas?.getContext('2d', { alpha: true });
    }

    public update(): void {
        if (!this.shouldUpdate() || !this._vectorScopeContext) {
            return;
        }

        this.tempCanvas.width = this.imageElement.naturalWidth;
        this.tempCanvas.height = this.imageElement.naturalHeight;
        this.tempCtx?.drawImage(this.imageElement, 0, 0, this.tempCanvas.width, this.tempCanvas.height);

        const data = this.tempCtx?.getImageData(0, 0, this.tempCanvas.width, this.tempCanvas.height).data || [];

        const center = this._size / 2;
        const radius = this._size * 0.48;

        // Clear vectorscope canvas
        this._vectorScopeContext.clearRect(0, 0, this._size, this._size);

        // Prepare image buffer for fast pixel plotting
        const vImageData = this._vectorScopeContext.createImageData(this._size, this._size);
        const vData = vImageData.data;

        // Draw background circle
        for (let y = 0; y < this._size; y++) {
            for (let x = 0; x < this._size; x++) {
                const dx = x - center;
                const dy = y - center;
                const dist = Math.sqrt(dx * dx + dy * dy);
                const idx = (y * this._size + x) * 4;
                if (dist <= radius) {
                    vData[idx] = 51;
                    vData[idx + 1] = 51;
                    vData[idx + 2] = 51;
                    vData[idx + 3] = 229; // 0.9 * 255 ≈ 229
                } else {
                    vData[idx + 3] = 0; // transparent outside the circle
                }
            }
        }

        // Downsample for speed (step by 4 or 8)
        for (let i = 0; i < data.length; i += 4 * 8) {
            const r = this.limitedRgbToFullRGB(data[i]),
                g = this.limitedRgbToFullRGB(data[i + 1]),
                b = this.limitedRgbToFullRGB(data[i + 2]);
            // Convert RGB to YUV (BT.601)
            const u = -0.14713 * r - 0.28886 * g + 0.436 * b;
            const v = 0.615 * r - 0.51499 * g - 0.10001 * b;
            // Normalize U,V to [-1,1]
            const uNorm = u / 112;
            const vNorm = v / 157;
            // Map to canvas coordinates
            const x = Math.round(center + uNorm * radius);
            const y = Math.round(center - vNorm * radius);
            if (x >= 0 && x < this._size && y >= 0 && y < this._size) {
                const idx = (y * this._size + x) * 4;
                vData[idx] = r;
                vData[idx + 1] = g;
                vData[idx + 2] = b;
                vData[idx + 3] = 255; // alpha
            }
        }
        this._vectorScopeContext.putImageData(vImageData, 0, 0);
    }

    public clear(): void {
        this._vectorScopeContext?.clearRect(0, 0, this._size, this._size);
    }
}

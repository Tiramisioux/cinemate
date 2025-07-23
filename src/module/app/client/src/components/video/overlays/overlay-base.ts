export abstract class OverlayBase {
    public name: string = '';

    protected upDateRateFPS: number = 25;
    protected imageElement: HTMLImageElement;
    
    protected tempCanvas: HTMLCanvasElement;
    protected tempCtx: CanvasRenderingContext2D | null;

    private _lastUpdate: number = 0;
    private _enabled: boolean = false;
    constructor(imageElement: HTMLImageElement) {
        this.imageElement = imageElement;

        this.tempCanvas = document.createElement('canvas');
        this.tempCtx = this.tempCanvas.getContext('2d', { willReadFrequently: true });
    }

    public update(): void {}

    public set enabled(enabled: boolean) {
        this._enabled = enabled;
        if (!this._enabled) {
            this.clear();
        }
    }

    public get enabled(): boolean {
        return this._enabled;
    }

    public clear(): void {}

    protected shouldUpdate(): boolean {
        if (!this.enabled) {
            return false;
        }
        const now = performance.now();
        if (now - this._lastUpdate < 1000 / this.upDateRateFPS) {
            return false;
        }
        this._lastUpdate = now;

        return true;
    }

    protected limitedRgbToFullRGB(v: number): number {
        // Clamp to [16, 235] just in case
        v = Math.max(16, Math.min(235, v));
        // Map [16, 235] to [0, 255]
        return Math.round(((v - 16) * 255) / (235 - 16));
    }
}

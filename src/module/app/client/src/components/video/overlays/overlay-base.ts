export abstract class OverlayBase {
    public name: string = '';

    protected upDateRateFPS: number = 25;
    protected videoCanvas: HTMLCanvasElement;
    protected videoContext: CanvasRenderingContext2D;

    private _lastUpdate: number = 0;
    private _enabled: boolean = false;
    constructor(videoCanvas: HTMLCanvasElement, videoContext: CanvasRenderingContext2D) {
        this.videoCanvas = videoCanvas;
        this.videoContext = videoContext;
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

    protected limiteRgbToFullRGB(v: number): number {
        // Clamp to [16, 235] just in case
        v = Math.max(16, Math.min(235, v));
        // Map [16, 235] to [0, 255]
        return Math.round(((v - 16) * 255) / (235 - 16));
    }
}

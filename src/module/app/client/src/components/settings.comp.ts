import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';

import './slider.comp';
import { Exposure } from './video/overlays/exposure.overlay';
import { FocusPeaking } from './video/overlays/focus-peaking.overlay';

export enum SettingsKey {
    FocusPeakingThreshold = 'focus-peaking-threshold',
    ZebraStripesThreshold = 'zebra-stripes-threshold',
}

@customElement('cinemate-settings')
export class CinemateSettings extends LitElement {
    static styles = css`
        .button {
            border: none;
            appearance: none;
            cursor: pointer;
            padding: 0;
            display: block;
            width: 21px;
            height: 21px;
            background-color: var(--color-light);
            -webkit-mask-image: var(--icon-settings);
            mask-image: var(--icon-settings);
            -webkit-mask-repeat: no-repeat;
            mask-repeat: no-repeat;
            -webkit-mask-size: 100% 100%;
            mask-size: 100% 100%;
        }
        dialog {
            left: 0;
            top: var(--top-bar-height);
            height: calc(100vh - var(--top-bar-height) - var(--bottom-bar-height));
            background: var(--color-dark-transparent);
            color: var(--color-light);
            border: none;
            margin: 0;
            padding: 12px 20px;
            box-sizing: border-box;
            transition: 0.2s;
        }
        dialog::backdrop {
            background: transparent;
        }
        h2 {
            margin: 0 0 12px;
        }
    `;

    private static _cache: Map<string, string> = new Map<string, string>();

    private get _dialogElement(): HTMLDialogElement | null {
        return this.renderRoot.querySelector('dialog');
    }

    private _toggleDialog() {
        if (this._dialogElement?.open) {
            this._closeDialog();
        } else {
            this._openDialog();
        }
    }

    private _closeDialog() {
        this._dialogElement!.style.left = `-${this._dialogElement!.getBoundingClientRect().width}px`;
        this._dialogElement!.addEventListener(
            'transitionend',
            () => {
                this._dialogElement?.close();
            },
            { once: true }
        );
    }

    private _openDialog() {
        this._dialogElement!.style.left = `-100%`;
        this._dialogElement?.showModal();
        this._dialogElement!.style.left = `-${this._dialogElement!.getBoundingClientRect().width}px`;
        this._dialogElement!.style.left = `0`;
    }

    private _onDialogClick(e: MouseEvent): void {
        const rect = this._dialogElement?.getBoundingClientRect() || new DOMRect();

        // If clicked outside the dialog content, close it
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
            this._closeDialog();
        }
    }

    private _onSliderChanged(e: CustomEvent): void {
        const value = e.detail.value;
        const settingsKey = (e.target as HTMLElement).dataset.settingsKey;
        if (settingsKey) {
            CinemateSettings.SaveSetting(settingsKey, value);
        }
    }

    public static SaveSetting(key: string, value: string): void {
        window.localStorage.setItem(key, value);
        CinemateSettings._cache.set(key, value);
    }

    public static LoadSetting(key: string): string | null {
        const cachedValue = CinemateSettings._cache.get(key);
        if (cachedValue !== undefined) {
            return cachedValue;
        }
        return window.localStorage.getItem(key);
    }

    public static LoadSettingAsInt(key: string, defaultValue: number = 0): number {
        const value = CinemateSettings.LoadSetting(key);
        const parsed = parseInt(value ?? '');
        return Number.isNaN(parsed) ? defaultValue : parsed;
    }

    render() {
        return html`
            <button @click="${this._toggleDialog}" class="button"></button>
            <dialog @click="${this._onDialogClick}">
                <h2>Settings</h2>
                <cinemate-slider
                    @slider-changed="${this._onSliderChanged}"
                    data-settings-key="${SettingsKey.FocusPeakingThreshold}"
                    min="${FocusPeaking.MinThreshold}"
                    max="${FocusPeaking.MaxThreshold}"
                    value="${CinemateSettings.LoadSettingAsInt(
                        SettingsKey.FocusPeakingThreshold,
                        FocusPeaking.DefaultThreshold
                    )}"
                    label="Peaking Threshold"
                ></cinemate-slider>
                <cinemate-slider
                    @slider-changed="${this._onSliderChanged}"
                    data-settings-key="${SettingsKey.ZebraStripesThreshold}"
                    min="${Exposure.MinThreshold}"
                    max="${Exposure.MaxThreshold}"
                    value="${CinemateSettings.LoadSettingAsInt(
                        SettingsKey.ZebraStripesThreshold,
                        Exposure.DefaultThreshold
                    )}"
                    label="Zebra Threshold"
                ></cinemate-slider>
            </dialog>
        `;
    }
}

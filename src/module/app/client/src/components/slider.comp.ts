import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { Color } from './app.const';

@customElement('cinemate-slider')
export class CinemateSlider extends LitElement {
    static styles = css`
        label {
            display: block;
            margin-bottom: 0.5rem;
        }
        .value-label {
            font-weight: 700;
            display: inline-block;
            width: 3rem;
        }
        #slider {
            width: 100%;
        }
    `;

    @property({ type: Number })
    min: number = 0;

    @property({ type: Number })
    max: number = 100;

    @property({ type: Number })
    value: number = 50;

    @property({ type: String })
    label: string = 'Slider';

    private _onInput(event: Event): void {
        const input = event.target as HTMLInputElement;
        this.value = Number(input.value);
        this.dispatchEvent(
            new CustomEvent('slider-changed', {
                detail: { value: this.value },
            })
        );
    }

    render() {
        return html`<label for="slider"> ${this.label}: <span class="value-label">${this.value}</span></label>
            <input
                id="slider"
                type="range"
                min="${this.min}"
                max="${this.max}"
                value="${this.value}"
                @input=${this._onInput}
                @change=${this._onInput}
            />`;
    }
}

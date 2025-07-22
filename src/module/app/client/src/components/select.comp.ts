import { html, css, LitElement } from 'lit';
import { customElement, property } from 'lit/decorators.js';

export type Options = Option[];

type Option = {
    value: string;
    label?: string;
};

@customElement('cinemate-select')
export class CinemateSelect extends LitElement {
    static styles = css`
        label {
            color: var(--color-dark);
            font-size: 0.7317rem;
            vertical-align: text-top;
        }
        select {
            background: black;
            color: var(--color-light);
            border: none;
            font-size: 1rem;
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
            position: relative;
            outline: none;
            cursor: pointer;
            font-weight: 700;
            font-family: 'Din2014';
        }
    `;

    @property({ type: String })
    label: string = '';

    @property({ type: String })
    suffix: string = '';

    @property({ type: String })
    selected: string = '';

    @property({ attribute: false })
    options: Options = [];

    private _onChange(event: Event) {
        const selectElement = event.target as HTMLSelectElement;
        this.selected = selectElement.value;
        this.dispatchEvent(
            new CustomEvent('change', {
                detail: { value: this.selected },
                bubbles: true,
                composed: true,
            })
        );
    }

    render() {
        this.options = this.options.length > 0 ? this.options : [{ value: 'N/A' }];
        return html` <label for="cinemate-select">${this.label}</label>
            <select id="cinemate-select" .value="${this.selected}" @change="${this._onChange.bind(this)}">
                ${this.options.map((option) => {
                    return html`<option
                        value="${option.value.toString()}"
                        ?selected=${option.value.toString() === this.selected}
                    >
                        ${option.label ? option.label : option.value}${this.suffix}
                    </option>`;
                })}
            </select>`;
    }
}

import { html, css, LitElement } from 'lit';
import { customElement, property } from 'lit/decorators.js';

@customElement('cinemate-info')
export class CinemateInfo extends LitElement {
    static styles = css`
        .label {
            color: var(--color-dark);
            font-size: 0.7317rem;
        }
        .value {
            color: var(--color-light);
            font-weight: 700;
            font-family: 'Din2014';
            margin-left: 4px;
        }
    `;

    @property({ type: String })
    label: string = '';

    @property({ type: String })
    value: string = '';

    render() {
        this.value = this.value.trim() || 'N/A';
        return html`<span class="label">${this.label}</span><output class="value">${this.value}</output>`;
    }
}

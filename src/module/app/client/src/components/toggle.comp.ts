import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { Color } from './app.const';

@customElement('cinemate-toggle')
export class CinemateToggle extends LitElement {
    static styles = css`
        .switch {
            position: relative;
            width: 32px;
            height: 16px;
            border: 2px solid var(--toggle-color);
            border-radius: 34px;
        }

        .switch::before {
            content: '';
            position: absolute;
            width: 12px;
            height: 12px;
            top: 2px;
            left: var(--toggle-left);
            background-color: var(--toggle-color);
            border-radius: 50%;
            transition: 0.2s;
        }
    `;

    @property({ type: Boolean })
    active: boolean = false;

    protected update(changedProperties: PropertyValues): void {
        if (changedProperties.has('active')) {
            this.style.setProperty('--toggle-left', this.active ? '18px' : '2px');
            this.style.setProperty('--toggle-color', this.active ? Color.Green : Color.Dark);
        }
        super.update(changedProperties);
    }

    render() {
        return html`<div class="switch"></div>`;
    }
}

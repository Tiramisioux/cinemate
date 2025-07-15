import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { Color } from './app.const';

export enum RecStatus {
    Recording = 'red',
    Standby = 'black',
    FrameDrop = 'purple',
    BufferFull = 'yellow',
    Buffering = 'green',
}

const statusData = {
    [RecStatus.Recording]: {
        color: Color.Red,
        label: 'REC',
    },
    [RecStatus.Standby]: {
        color: Color.Green,
        label: 'STBY',
    },
    [RecStatus.FrameDrop]: {
        color: Color.Purple,
        label: 'F-DROP',
    },
    [RecStatus.BufferFull]: {
        color: Color.Yellow,
        label: 'BUFF-FULL',
    },
    [RecStatus.Buffering]: {
        color: Color.Blue,
        label: 'BUFF',
    },
};

@customElement('cinemate-rec-button')
export class CinemateRecButton extends LitElement {
    static styles = css`
        :host {
            color: var(--status-color);
            display: flex;
            align-items: center;
        }
        .circle {
            display: inline-block;
            width: 0.8rem;
            height: 0.8rem;
            border-radius: 50%;
            background-color: var(--status-color);
        }
        .value {
            font-weight: 700;
            font-family: 'Din2014';
            margin-left: 4px;
        }
    `;

    @property({ type: String })
    status: RecStatus = RecStatus.Standby;

    @state()
    private _label: string = statusData[this.status].label;

    protected update(changedProperties: PropertyValues): void {
        if (changedProperties.has('status')) {
            this.style.setProperty('--status-color', statusData[this.status].color);
            this._label = statusData[this.status].label;
        }
        super.update(changedProperties);
    }

    render() {
        return html`<span class="circle"></span><output class="value">${this._label}</output>`;
    }
}

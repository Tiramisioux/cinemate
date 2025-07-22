import { html, css, LitElement, PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';

import './toggle.comp';
import { IconUrl } from './app.const';

export type MenuOptions = MenuOption[];
export type MenuOption = {
    label: string;
    value: string;
    isToggle?: boolean;
    isToggled?: boolean;
    subLabel?: string;
};

@customElement('cinemate-menu')
export class CinemateMenu extends LitElement {
    static styles = css`
        .menu-button {
            border: none;
            appearance: none;
            cursor: pointer;
            padding: 0;
            display: block;
            width: 21px;
            height: 21px;
            background-color: var(--color-light);
            -webkit-mask-image: var(--menu-icon-url);
            mask-image: var(--menu-icon-url);
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
            padding: 0;
            transition: 0.2s;
        }
        dialog::backdrop {
            background: transparent;
        }
        .menu {
            padding: 0;
            margin: 0;
            list-style: none;
        }
        .menu li {
            padding: 12px 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 1rem;
            justify-content: space-between;
            border-bottom: 1px solid var(--color-darker);
        }
        .menu li:last-child {
            border-bottom: none;
        }
        .sub-label {
            font-size: 0.6rem;
            display: block;
        }
    `;

    @property({ attribute: false })
    options: MenuOptions = [];

    @property({ attribute: false })
    icon: IconUrl = IconUrl.Menu;

    private get _dialogElement(): HTMLDialogElement | null {
        return this.renderRoot.querySelector('dialog');
    }

    private _toggleMenu() {
        if (this._dialogElement?.open) {
            this._closeMenu();
        } else {
            this._openMenu();
        }
    }

    private _closeMenu() {
        this._dialogElement!.style.left = `-${this._dialogElement!.getBoundingClientRect().width}px`;
        this._dialogElement!.addEventListener(
            'transitionend',
            () => {
                this._dialogElement?.close();
            },
            { once: true }
        );
    }

    private _openMenu() {
        this._dialogElement!.style.left = `-100%`;
        this._dialogElement?.showModal();
        this._dialogElement!.style.left = `-${this._dialogElement!.getBoundingClientRect().width}px`;
        this._dialogElement!.style.left = `0`;
    }

    private onMenuItemClick(e: Event): void {
        const value = (e.currentTarget as HTMLElement).dataset.value;
        const optionClicked = this.options.find((option) => option.value === value);
        this.dispatchEvent(
            new CustomEvent('option-clicked', {
                detail: optionClicked,
            })
        );
        if (!optionClicked?.isToggle) {
            this._closeMenu();
        }
    }

    private _onDialogClick(e: MouseEvent): void {
        const rect = this._dialogElement?.getBoundingClientRect() || new DOMRect();

        // If clicked outside the dialog content, close it
        if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
            this._closeMenu();
        }
    }

    /* protected firstUpdated(_changedProperties: PropertyValues): void {
        super.firstUpdated(_changedProperties);
        this._dialogElement?.showModal();
    } */

    protected update(changedProperties: PropertyValues): void {
        super.update(changedProperties);
        this.style.setProperty('--menu-icon-url', this.icon);
    }

    render() {
        return html`
            <button @click="${this._toggleMenu}" class="menu-button"></button>
            <dialog @click="${this._onDialogClick}">
                <menu class="menu">
                    ${this.options.map((option) => {
                        return html`
                            <li data-value="${option.value}" @click="${this.onMenuItemClick}">
                                <div>
                                    <span class="label">${option.label}</span>
                                    ${option.subLabel ? html`<span class="sub-label">${option.subLabel}</span>` : null}
                                </div>
                                ${option.isToggle
                                    ? html`<cinemate-toggle ?active=${option.isToggled}></cinemate-toggle>`
                                    : null}
                            </li>
                        `;
                    })}
                </menu>
            </dialog>
        `;
    }
}

# GUI text

Every heading and description string the settings editor shows. **This is where that copy
lives.** `src/module/app/templates/settings_editor.html` holds no prose of its own — it asks
for each string by key, and `src/module/app/gui_text.py` answers from these files when
CineMate starts.

## Editing

- Change any heading line or any paragraph. That is what the browser shows.
- **Never change or remove a `<!-- key: ... -->` line.** The key is the link between this file
  and the template. A key the template asks for and cannot find renders as a red
  `[missing text: ...]` marker in the page, and fails `tools/gui_text_check.py` in CI.
- Restart CineMate to see a change. These files are read once, at startup.

### Formatting

| You write | The page shows |
|---|---|
| `` `config.txt` `` | `config.txt` in the monospace face |
| `**Cycle through the list**` | bold |
| `*down*` | italic |
| `[Value steps](#steps){data-nav}` | a link to that pane |

The brace group on a link carries the attributes the anchor needs — `data-nav` for the
sidebar's scrollspy, `data-open-config` for the button that opens the reconstructed
`config.txt`. Leaving it off produces a link that looks right and does nothing.

Anything else is escaped, so a `<` in a sentence stays a `<`.

## What a key means

The heading line above a key and the paragraph below it are two different strings. Which is
which depends on the prefix:

| Prefix | What it is | Heading line | Paragraph |
|---|---|---|---|
| `tab.` | a page tab across the top | the tab label | the small hint under it |
| `rail.` | a sidebar group | the group title | the blurb under it |
| `raillink.` | one sidebar link | the link label | — |
| `pane.` | a pane | the pane heading | the description under it |
| `card.` | one setting card | the setting name | the help text under it |
| `caption.` | the small captions on a card's controls | — | one line, `·` separated |
| `note.` | a note box | — | the note |
| `warn.` | an inline warning, shown only when it applies | — | the warning |
| `help.` | help text not attached to a card | — | the text |
| `text.` | any other prose in a pane | — | the text |

`_(no pane description)_` and similar italic lines mark a string that is deliberately absent.
They are notes to whoever edits the file; they are not rendered. Replace one with a real
sentence to add that string.

## Files

One file per sidebar group, in sidebar order. `00-chrome.md` holds the tabs and the sidebar
itself.

## What is not in here

Strings JavaScript builds at runtime — i2c device detail lines, toast messages, most
empty and error states on the RAW-files and controls panes — and the four first-paint status
strings the script immediately rewrites (`cfgStatusText`, `statusText`, `pbLockBody`,
`pbLockTitle`). Those live in the script. Short control labels (button text, `.eyebrow`
captions) are still in the template.

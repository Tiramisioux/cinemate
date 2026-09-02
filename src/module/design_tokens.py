"""Single source for colours shared between the HDMI GUI (simple_gui.py) and
the web GUI's CSS custom properties (app/templates/template.html).

ADR-001 option B, step 1 (system-review/decisions/ADR-001-gui-harmonization.md
section 6, "one token source generating the Python constants and the CSS
custom properties"). Before this module, the two sides were two
independently hand-maintained lists, kept in agreement only by a comment
naming which CSS token mirrors which Python constant -- and the review found
three of those comments already drifted. tools/design_token_diff.py checks
that template.html's `:root` block still matches this dict exactly.

Only tokens with a genuine counterpart on both sides live here. Two CSS
custom properties (--box-text, --sync-tint) and one Python colour
(SYNC_FLASH_COLOR, a PIL-only "magenta" name string, not an RGB tuple) have
no equivalent on the other side and stay defined locally where they're used
-- forcing them into this shared table would invent a link that isn't real.
"""

DESIGN_TOKENS = {
    "label": (136, 136, 136),  # status-box / field-label grey
    "box": (136, 136, 136),  # status-box border -- same grey as label
    "value": (249, 249, 249),  # default label-value text colour
    "guide": (249, 249, 249),  # preview-guide outline, un-zoomed state
    "zoom_hi": (255, 221, 0),  # preview-guide outline once zoomed in
    "drop": (120, 40, 180),
    "drop_text": (255, 255, 255),  # W3: black-on-purple was 2.76:1, fails AA
    "sync": (255, 0, 255),
    "log_badge": (205, 205, 205),
    "hdr_badge": (205, 205, 205),
    "sdr_badge": (120, 120, 120),
    "wav_rec": (210, 210, 210),
    "res_switching": (176, 176, 176),
    "lock": (255, 0, 0),
    "voltage": (218, 149, 77),
}

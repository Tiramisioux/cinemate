# Resume prompt — Cinemate settings editor UI concept

Paste the block below into a fresh thread to pick this back up. It is self-contained.

---

```
/cinepi-cinemate-review

Continue the Cinemate settings editor web UI concept. We are still in mockup mode — this
is a design sketch, not an implementation task. Read the file before doing anything else:

  cinemate/dev-notes/settings-editor-ui/concept.html

It's a single self-contained HTML file (inline CSS/JS, no build step, no backend) —
open it directly, or serve it with the `settings-editor-preview` entry already in
.claude/launch.json (points at this same directory) and use the Claude_Preview tools.
It is also published as a Claude Artifact — ask me for the URL if you need to redeploy
to the same one instead of minting a new one.

WHAT IT IS
A 4-pane pedagogical editor: config.txt | settings.jsonc | RAW files | Live view.
- config.txt pane: per-port sensor overlay pickers, RP1 overclock, hardware interface
  toggles, live-reconstructed raw file preview.
- settings.jsonc pane: every field grouped into sections ordered to match the real
  file's top-level key sequence (system → sensors → settings → arrays → image_capture →
  audio_capture → hdmi_display → hardware_controls → input_peripherals →
  hardware_outputs → output_peripherals). Buttons/switches/quad-rotary actions are real
  method+arg pickers sourced from src/module/cli_commands.py's command table, with a
  manual-entry fallback and GPIO pin remapping (conflict-aware, confirm dialog). A live
  JSON preview drawer reconstructs the actual file shape as you edit, including
  hardware_controls / input_peripherals.quad_rotary_controller.
- RAW files pane: browse/download/delete mock takes.
- Live view pane: a browser mirror of simple_gui.py's on-camera HDMI overlay.
- Single visual skin — always the black/DIN2014 HUD look (quotes simple_gron_gui.py
  directly); the Manual/paper skin was removed by request.

SOURCE OF TRUTH IT WAS BUILT AGAINST
- cinemate/settings.jsonc on branch feature/settings-jsonc (that branch may have moved
  or merged since — diff against it, don't assume it's still current)
- cinemate/src/module/cli_commands.py for the method/argument list on the action pickers

WHAT'S KNOWINGLY NOT MODELED (gaps, not bugs)
- system.web_api, system.storage.recognized_ssds, image_capture.custom_modes — skipped
  as separate scope, never built
- hardware_outputs.pwm_pin — mentioned by the user as part of the real schema, never
  added to the mockup
- Free mode + increment on ISO/shutter/FPS/WB and the 4 ClearHDR knobs is an INVENTED
  mockup extension (arrays.*.free_increment, image_capture.hdr.*_free /
  *_free_increment) — not in the real settings.jsonc schema. If real implementation
  ever follows this concept, that needs a real schema decision first, not just a port.
  (button/switch/rotary actions ARE already wired into the live drawer via
  buildHardwareControlsState()/buildButtonLikeObject() — that part is done, not a gap)

HOW TO WORK
- This is still a static mockup: no server, no real Pi calls, everything simulated in
  client-side JS. Don't start building a real backend for it unless asked — that's a
  separate, much bigger decision (framework choice, auth, how it talks to redis/CLI on
  the Pi) that hasn't been made yet.
- If asked to keep iterating on the concept: edit concept.html directly, verify with the
  Claude_Preview tools (preview_start the settings-editor-preview config, preview_eval
  for interaction testing — many past bugs here were CSS grid/display:contents
  interactions, not JS logic; verify with getBoundingClientRect() assertions, not just
  "did it run"), then use the Artifact tool to redeploy to the existing URL.
- If asked to scope real implementation: that's a new conversation — don't conflate it
  with this file. Start by asking what the actual delivery target is (does this become
  part of the Flask app already serving the live view at :5000, a separate service,
  etc.) before writing any real code.
```

---

## Notes for whoever pastes this

- Unlike `recovery-console`/`web-api`, this workspace deliberately has **no IMPLEMENTATION-PLAN.md and no feature branch**. Nothing here is committed — it's still exploratory mockup work, not a scoped implementation with phases and gates. Don't invent phases/gates for it until the user actually decides to build the real thing.
- The concept file is large (single HTML file, several hundred KB with embedded fonts) — read it in sections if context is tight, or grep for the section you need (`<!-- STEPS -->`, `<!-- POTS`, etc. mark each settings.jsonc section; `<!-- BOOT CONFIG -->`, `<!-- CLIPS -->`, `<!-- LIVE VIEW -->` mark the other 3 panes).

# How “inverse” (1-0-1) buttons are auto-detected
Many latching push-buttons are wired closed = logic 1 at rest and open = 0 when pressed. At start-up each SmartButton performs:

```python
if self.button.is_pressed:      # high at rest → treat as “inverse”
    self.inverse = True
```

If so, the framework swaps the handlers:

```
when_pressed  ← on_release
when_released ← on_press
```
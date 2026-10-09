# Configuration

Profiles are TOML files. The built-in **`jingan`** profile ships with the package (`src/grbl_pen_plotter/data/jingan.toml`) and is also mirrored under `profiles/` in the repo.

```bash
penplot status --profile jingan
penplot stream job.gcode --profile ./my-machine.toml
```

## Sections

### `[pen]`

| Key | Meaning |
|-----|---------|
| `mode` | `z_stepper` (default) or `servo_pwm` |
| `z_up` | Work Z for pen-up (usually `0` after `G92` at raised) |
| `z_down` | Work Z for pen-down (JinGan calib: `15`) |
| `z_feed` | Feed for Z moves |
| `spindle_on` / `spindle_off` | Usually `M3 S1000` / `M5` — keeps PWM asserted while down |
| `hold_spindle_during_stroke` | Emit spindle_on before each stroke |

**JinGan polarity:** after parking at *raised* height and `G92`, pen-down is **Z+**. Other machines may invert Z via `$3`.

### `[feeds]`

`rapid`, `draw`, `jog` in mm/min.

### `[limits]`

Sender-side soft limits (mm). Streaming and converters refuse paths outside these bounds (minus `margin`).

Optional `machine_*` fields clamp **machine** coordinates when you pass `--g92x/--g92y` (origin in machine space). Useful when the physical bed is larger than the paper work box.

### `[grbl]`

| Key | Meaning |
|-----|---------|
| `baud` | Default `115200` |
| `step_idle_plotting` | `$1` while plotting (`255` = never disable steppers) |
| `step_idle_cool` | `$1` after jobs (`25`) to reduce motor heat |
| `laser_mode` | Must stay `0` for pens (`$32=0`) |
| `soft_reset_on_connect` | Send `0x18` on connect |
| `home_on_connect` | Always `false` for unhomed JinGan units |

## Creating a variant

Copy `profiles/jingan.toml`, retune `z_down` with 1 mm steps from a raised zero, and adjust `limits` to your sheet. Do not enable GRBL `$20` soft limits unless homing (`$22`) works on your firmware.

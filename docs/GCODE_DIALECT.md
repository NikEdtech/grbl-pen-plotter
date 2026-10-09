# G-code dialect (JinGan / GRBL pen plotters)

Target firmware: **GRBL 1.3a** class (BtWriter / JinGan OEM). Not LinuxCNC, not Marlin.

## Units and modes

```
G21   ; mm
G90   ; absolute
G94   ; units/min
```

## Pen up / down (stepper Z — recommended)

After manual park at sheet corner with pen **raised**, set work zero:

```
G92 X0 Y0 Z0
```

Then:

| Action | Commands |
|--------|----------|
| Pen down | `M3 S1000` then `G0 Z15` (tune Z) |
| Draw | `G1 X… Y… F…` while M3 stays on |
| Pen up | `G0 Z0` then `M5` / `S0` |

On JinGan, **`$1=255`** keeps steppers energized at Idle so the pen does not spring back. After a job, set **`$1=25`** to cool motors.

## Servo PWM variant

Some vendor forks use angle-like `S0`–`S12` with `M3` and little or no Z travel. Stock GRBL spindle PWM is **not** a 50 Hz hobby servo. Use a matching firmware if your machine is servo-only. This project’s default profile assumes a **real Z axis**.

## Realtime

| Byte | Meaning |
|------|---------|
| `0x18` | Soft reset |
| `!` | Feed hold |
| `~` | Cycle start / resume |
| `?` | Status report |

Soft-reset clears `G92`. Re-park and re-zero before the next job.

## Do not

- Enable **`$32=1`** (laser mode) for pen work — motion/power coupling breaks pen recipes.
- Enable **`$20=1`** soft limits without working homing (`$22`).
- Command absolute machine `G0 Z0` before `G92` when MPos Z is large (hundreds) — that can crash into the bed. Always `G92` at the raised pose first.

## Streaming

This tool sends one line at a time and waits for `ok` / `error` / `ALARM`. On alarm it soft-resets and attempts pen-up. Comments (`;…`) and blank lines are stripped before send.

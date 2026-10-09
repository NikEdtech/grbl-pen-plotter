# Troubleshooting

## Lost position / mirrored drawing

**Cause:** Unhomed machine (`$22=0`). Soft-reset clears `G92`. Jogging without a known origin drifts.

**Fix:**

1. Raise the pen to max height.
2. Manually move the carriage to the sheet corner you want as origin.
3. `penplot zero` (or `G92 X0 Y0 Z0`).
4. If Latin text comes out mirrored, regenerate with `--flip-x` / `--flip-y`.

## Pen not touching paper

- Confirm work zero was set at **raised** height, not mid-air after a previous down move.
- Increase `z_down` in 1 mm steps (JinGan calib settled at **15** after mount adjust).
- Ensure `$1=255` while plotting so the pen holds down at Idle.
- Keep `M3 S1000` asserted for the stroke; lift with `M5` after `Z` up.

## Pen snaps back up at Idle

`$1` (step idle delay) was too small (e.g. `25`). GRBL disables steppers and the spring lifts the pen while MPos still shows “down”. Set `$1=255` for the job; cool with `$1=25` afterward (`penplot stream … --cool`).

## Laser mode / weird S behavior

Check `$32`. For pens it must be **`0`**. Laser mode changes how `S` and motion interact.

## Port not found (macOS)

- Use a **data** USB cable / hub (charge-only cables often fail).
- Prefer `/dev/cu.usbserial-*` over `/dev/tty.usbserial-*`.
- `penplot ports` lists candidates; pass `--port` explicitly.

## Alarm mid-job

Streamer aborts, soft-resets, and tries pen-up. Clear with `$X` after fixing the mechanical cause. Re-zero (`G92`) after every soft-reset.

## Stipple looks like worms

Experimental path: dense points stay pen-down under `lift_threshold`, which draws dashes between dots. Lower `--points`, raise `--lift-threshold` only for true travel, or use a lighter `z_down` (e.g. 13). Prefer SVG line art / handwriting for reliable results.

# Hardware test checklist

Use when the plotter is plugged in. The automated path is:

```bash
penplot hwtest --profile jingan
```

If no CH340 / `cu.usbserial*` port is present, the command exits and you can run this checklist manually later.

## Before you start

- [ ] Data USB cable to Mac; `ls /dev/cu.usbserial*` shows a device
- [ ] 12 V power connected to the plotter
- [ ] Paper taped flat; pen installed and can reach the sheet when lowered
- [ ] Carriage parked at the **sheet corner** with pen at **maximum height**
- [ ] No other app holding the serial port

## Safe sequence

1. **Ports** — `penplot ports` (autodetect marked with `*`)
2. **Status** — `penplot status` → expect `Idle` and an `MPos`/`WPos` triple
3. **Zero** — `penplot zero` (raises pen, then `G92 X0 Y0 Z0`)
4. **Jog** — `penplot jog X 1` then `penplot jog X -1` (1 mm nudge)
5. **Pen cycle** — `penplot pen down` → confirm mark/pressure → `penplot pen up`
6. **Small plot** — generate and stream a ≤60×60 mm job from the current origin:

```bash
penplot text "Test Тест" -o /tmp/test.gcode --em 0.3 --ox 5 --oy 5 --max-width 50 --preview /tmp/test.png
# Also draw a square via SVG or combine manually; hwtest does both.
penplot stream /tmp/test.gcode --set-zero --cool
```

Or simply: `penplot hwtest` (square 50 mm + «Test Тест», aborts on alarm).

## After the job

- [ ] Pen is up; carriage Idle
- [ ] `$1` cooled to 25 if you used `--cool`
- [ ] Soft-reset → re-zero before the next job

## Stop immediately if

- GRBL reports `ALARM`
- Unusual noise / binding
- Pen driving past the sheet edge

Use feed hold (`!`) from a connected session, or unplug power as last resort.

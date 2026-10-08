# Contributing

Thanks for helping! Reports from other installations are the most valuable contribution –
this integration has been tested on a single system so far.

## Reporting what your controller does

- Open an issue with your firmware versions (shown by the update entities) and, if possible,
  the **diagnostics download** of the integration (Settings → Devices & services → the
  integration → ⋮ → Download diagnostics). It redacts PSK, host and device ID.
- **Never post your PSK**, BLE address or anything from `tools/e16_onboard.py --output`.
- Raw packets are welcome; replace zone and device names if you like.

## Code

- Keep `custom_components/inventer_e16/client.py` free of Home Assistant imports.
- Add a test in `tests/` for every protocol change (`pip install pytest && pytest tests`).
- New entity names and states go into `strings.json`, `translations/en.json` and
  `translations/de.json`.
- Mark protocol knowledge in `docs/protocol.md` as *verified* only if you checked it on a device.
- Do not add code, images, icons or other assets of the manufacturer or its app.

## Pull requests

One topic per pull request, with a short note on how you tested it (device, firmware).

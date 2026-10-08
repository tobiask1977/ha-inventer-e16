# Instructions for AI agents and contributors

Home Assistant custom integration `inventer_e16` for the inVENTer Easy Connect e16 ventilation
controller. It speaks the controller's local "Zirconia" protocol over TLS-PSK on TCP 47820.
Read [README.md](README.md) and [docs/protocol.md](docs/protocol.md) before changing anything.

## Layout

| Path | Content |
|---|---|
| `custom_components/inventer_e16/client.py` | Protocol client – **no Home Assistant imports**, testable on its own |
| `custom_components/inventer_e16/coordinator.py` | Polling: zone every 30 s, maintenance/firmware every 10 min, vendor catalog daily |
| `custom_components/inventer_e16/<platform>.py` | Entities (sensor, binary_sensor, fan, button, number, select, update) |
| `custom_components/inventer_e16/strings.json`, `translations/` | Entity names and states (English, German) |
| `tests/test_client.py` | Protocol tests with anonymised real replies (`pytest tests`) |
| `tools/e16_onboard.py` | BLE tool to read device ID and PSK |
| `docs/protocol.md`, `docs/onboarding.md` | Protocol reference, pairing guide |

## Rules

1. **No secrets or personal data – ever.** No PSK, PIN, TLS identity, device ID, BLE/Wi-Fi MAC
   address, IP address, zone or room names from a real installation – not in code, tests,
   docs, commit messages or issues. Test data uses anonymised replies (names and timestamps
   replaced, CRC recalculated). Scan the diff before every push.
2. **No manufacturer material.** No code, images, icons, logos, screenshots or long text taken
   from the official app or website. Describe protocol facts in your own words. Short generic
   labels (e.g. profile names) are fine.
3. **Verified vs. inferred.** In `docs/protocol.md`, call something *verified* only if it was
   checked on a real controller; otherwise say where it comes from.
4. **Writes to a real device need the owner's consent.** Reading is harmless; commands change
   how a ventilation system in an inhabited building runs.
5. **Two mode tables.** The zone status reports 1 = ventilation, 2 = heat recovery; the
   UserOverride command uses 1 = heat recovery, 2 = ventilation. Convert via `READ_MODE_TO_FAN`.
6. **Untrusted replies.** Everything parsed from the controller or the vendor cloud must end in a
   `ValueError`/`OSError` on bad input, never in an unhandled exception.
7. **Translations.** New entities get a `translation_key`; add name and states to
   `strings.json`, `translations/en.json` and `translations/de.json`. State values are keys
   (`heat_recovery`), not display text.
8. **Keep unique IDs stable.** `<device_id>_<key>` and `<device_id>_<address>_<key>` – changing a
   key orphans the user's entities.

## Before a release

- `pytest tests --ignore=tests/ha` passes; CI (tests, ha-tests, hassfest, HACS) is green.
- Bump `version` in `manifest.json` and add a `CHANGELOG.md` entry.
- If possible, import all platforms against the targeted Home Assistant version in a venv
  (`pip install homeassistant==<version>`) and evaluate the entities with sample data.

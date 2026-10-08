# Security Policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) instead. You will get an answer
within a week.

## Keys and credentials

The PSK of an Easy Connect e16 allows controlling the ventilation from the local network.
Never include it in issues, logs or screenshots. If you posted it by accident, delete the post
and treat the key as known – it cannot be changed by the user, so keep the controller in a
separate network segment (e.g. an IoT VLAN) that untrusted devices cannot reach.

## Threat model

| Topic | How it is handled |
|---|---|
| Local connection | TLS 1.2 with a pre-shared key (`PSK-AES128-CBC-SHA`), as dictated by the device. PSK suites authenticate both sides, so no certificate is checked. No forward secrecy – a leaked PSK also decrypts recorded traffic. |
| Key storage | The PSK lives in the Home Assistant config entry like any other integration credential (`.storage`, part of HA backups). It is never logged; the diagnostics download redacts PSK, host and device ID. |
| Replies from the controller | Treated as untrusted: length, CRC and packet type are checked, truncated or garbled replies end as a handled error, and the number of radio devices queried is capped. |
| Vendor firmware catalog | Optional HTTPS request (certificate verified) once a day that sends only the brand name. Only integer versions are accepted from the reply. Disable it in the integration options. |
| Onboarding tool | Reads the key over Bluetooth only in pairing mode, which needs physical access to the controller. With `--output` the file is created readable for the owner only (POSIX). |
| Commands | Only the commands the official app uses, with the app's value ranges (speed 1–4, 15 min–8 h). "Off" pauses the ventilation without time limit, exactly like the app's power button. |
| Supply chain | No runtime dependencies besides Home Assistant. CI actions are pinned to commit SHAs and run with read-only permissions and without secrets. |

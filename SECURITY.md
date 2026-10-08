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

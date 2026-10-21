# Onboarding: reading device ID and PSK

*[Deutsche Fassung weiter unten.](#deutsch)*

The integration needs three values: the controller's **IP address**, its **device ID** and its
**PSK** (pre-shared key). The PSK is individual per controller and never shown by the official
app – but the controller hands it out over Bluetooth LE while it is in pairing mode. You do this
**once**; afterwards everything runs over Wi-Fi.

## What you need

- The Easy Connect e16 **with Wi-Fi module**, already connected to your Wi-Fi with the official
  app. Note its IP address (router/DHCP list) and reserve it there.
- A computer with **Bluetooth LE** (most laptops; a Raspberry Pi works too) and **Python 3.10+**.
- To be within a few metres of the controller.

## Steps

1. Install the Bluetooth library:

   ```bash
   pip install -r tools/requirements.txt
   ```

2. Put the controller into **pairing mode**: hold the **mode button for about 4 seconds** until
   the **LED blinks blue**. Pairing mode ends by itself after a while – if a step fails, start it
   again.

3. Find the controller:

   ```bash
   python tools/e16_onboard.py scan
   ```

   It lists controllers in range with their Bluetooth address and signal strength.

4. Read device ID and PSK:

   ```bash
   python tools/e16_onboard.py read                    # if exactly one controller was found
   python tools/e16_onboard.py read AA:BB:CC:DD:EE:FF  # otherwise with its address
   ```

   Output:

   ```text
   Device ID: ABCDE-FGHIJ
   PSK:       0123456789abcdef
   ```

   With `--output e16.secret.json` the values go to a file instead of the screen.

5. In Home Assistant: *Settings → Devices & services → Add integration → inVENTer Easy Connect
   e16*, enter IP address, device ID and PSK. The integration reads the zone once to check the
   key and names the device after the zone.

## Without Python: a BLE app on your phone

Instead of the tool you can read the two values with a generic Bluetooth LE app on your phone
(e.g. nRF Connect or a BLE scanner app; Android and iOS). Nothing needs to be installed on a computer.

1. Put the controller into **pairing mode** (LED blinks blue, see step 2 above).
2. In the app, scan and connect to the controller (it appears as *Easy Connect e16*).
3. Among its services, find these two characteristics and **read** each once:

   | Value | Characteristic UUID | Shown as |
   |---|---|---|
   | Device ID | `673de933-963b-4298-bfc1-b0ccdada690a` | text (switch the app's display to text/UTF-8 if it shows bytes); ignore trailing zero bytes |
   | PSK | `638ff62c-3823-4e0f-8179-1695c46ee8ad` | 8 bytes in hex, e.g. `(0x) 01-23-45-67-89-AB-CD-EF` or `0123 4567 89AB CDEF` |

   Careful: a neighbouring characteristic differs only in the last character (`…8af`). The PSK is
   the one ending in **`…8ad`**. On iPhone/Mac the controller advertises only its name and the
   standard *Device Information* service – the two characteristics show up after connecting.

4. Enter both in Home Assistant. The PSK can be pasted as the app shows it – `0x`, dashes,
   colons and spaces are removed. If Home Assistant discovered the controller by itself, the
   device ID is already filled in and only the PSK is needed.

Only **read** – do not write to any characteristic. Read before anything confirms the pairing PIN
(otherwise the key comes back as zeros). Afterwards disconnect and clear the app's log, which may
contain the key.

## Good to know

- **`read` only reads.** It writes nothing to the controller, so your app keeps working as before.
  `--confirm-pin` additionally confirms the pairing PIN like the app does at the end of its own
  pairing – normally not needed.
- **Read before the PIN is confirmed.** After a PIN confirmation the controller returns zeros
  for identity and key until pairing mode is started again. The tool therefore reads first.
- **Keep the PSK private.** It allows controlling the ventilation from your network and cannot be
  changed. Put the controller into a network segment (e.g. an IoT VLAN) that untrusted devices
  cannot reach, and never post the key in issues or logs.
- If Home Assistant runs on hardware with Bluetooth near the controller, you can run the tool
  there as well – it is plain Python.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `scan` finds nothing | Not in pairing mode (LED must blink blue), too far away, or Bluetooth off. If a BLE app shows the controller, pass its address to `read` |
| "The controller returned an empty key" | The PIN was already confirmed in this pairing session (e.g. by the app). Start pairing mode again and run `read` right away |
| Connection drops on Windows | Windows caches incomplete Bluetooth service tables; the tool forces a fresh read. Toggle Bluetooth off/on and retry, or use Linux |
| Home Assistant: "Cannot reach the controller" | Wrong IP, controller not on Wi-Fi, or a firewall blocks TCP 47820 from Home Assistant to the controller |
| Home Assistant: "PSK invalid" | Typo, or the key was read after a PIN confirmation (all zeros) – read again |

---

## Deutsch

Die Integration braucht drei Werte: **IP-Adresse**, **Gerätekennung** und **PSK** des Reglers.
Der PSK ist je Regler verschieden und wird in der App nie angezeigt. Im Kopplungsmodus gibt der
Regler ihn aber über Bluetooth LE heraus. Das ist **einmalig** nötig, danach läuft alles über WLAN.

**Voraussetzungen:** Regler mit WLAN-Modul, per App im WLAN (IP-Adresse im Router reservieren);
ein Rechner mit Bluetooth LE und Python 3.10+; ein paar Meter Abstand zum Regler.

**Ablauf:**

1. `pip install -r tools/requirements.txt`
2. **Kopplungsmodus:** Modustaste am Regler etwa **4 Sekunden** halten, bis die **LED blau
   blinkt**. Der Modus endet nach einer Weile von selbst – bei Fehlern einfach neu starten.
3. `python tools/e16_onboard.py scan` – zeigt Regler in Reichweite mit Bluetooth-Adresse.
4. `python tools/e16_onboard.py read` (oder `read AA:BB:CC:DD:EE:FF`) – gibt Gerätekennung und
   PSK aus; mit `--output e16.secret.json` stattdessen in eine Datei.
5. In Home Assistant *Einstellungen → Geräte & Dienste → Integration hinzufügen → inVENTer Easy
   Connect e16*, IP-Adresse, Gerätekennung und PSK eintragen.

**Ohne Python, mit dem Handy:** Statt des Tools geht auch eine allgemeine Bluetooth-LE-App (z. B.
nRF Connect oder eine BLE-Scanner-App). Regler in den Kopplungsmodus bringen, in der App mit
*Easy Connect e16* verbinden und zwei Characteristics je einmal **lesen**: Gerätekennung
`673de933-963b-4298-bfc1-b0ccdada690a` (Text, Nullbytes am Ende ignorieren) und PSK
`638ff62c-3823-4e0f-8179-1695c46ee8ad` (8 Bytes hex, z. B. `(0x) 01-23-45-67-89-AB-CD-EF` oder
`0123 4567 89AB CDEF`; Achtung, eine Nachbar-Characteristic endet auf `…8af`). Den PSK
kann man so in Home Assistant einfügen, `0x`, Bindestriche und Doppelpunkte werden entfernt. Nichts
schreiben, und danach das Log der App löschen, weil der Schlüssel darin stehen kann.

**Wichtig:** `read` liest nur und ändert nichts am Regler – die App funktioniert weiter. Identität
und PSK müssen **vor** einer PIN-Bestätigung gelesen werden, danach liefert der Regler Nullen. Den
PSK geheim halten: Wer ihn kennt, kann die Lüftung aus dem Netz steuern, und er lässt sich nicht
ändern. Der Regler gehört deshalb in ein abgeschottetes Netz (z. B. IoT-VLAN).

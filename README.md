# ESP32 StreamLine for Home Assistant

[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lutyjj&repository=esp32-streamline-hacs&category=integration)

[![CI](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml)
[![HACS](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml)

This HACS integration connects Home Assistant directly to each
[ESP32 StreamLine](https://github.com/lutyjj/esp32-streamline) device. It does
not connect to the StreamLine bridge. The bridge still owns network playback,
recordings, and bridge-side transport configuration.

The integration polls the ESP32 locally every five seconds. It sends no data
to cloud services. A firmware update check asks the device to query its own
GitHub release source.

## Entities

Each ESP32 appears as one Home Assistant device.

| Entity | Purpose |
|---|---|
| Playing | Reports active audio capture. |
| Peak level | Reports the highest current input level. |
| Input, input gain, ADC attenuation | Control the device audio input. |
| Analog passthrough | Controls local analog output on supported boards. |
| Wi-Fi signal, health | Report connectivity and startup health. |
| PCM encryption | Reports whether the device-to-bridge audio transport uses TLS-PSK. |
| Firmware | Checks for and installs the latest StreamLine firmware release, with progress. |
| Automatic update schedule | Selects disabled, daily, or weekly device-managed updates. |
| OTA status | Reports update phase, message, rollback availability, and the persisted last attempt. |
| Network errors, reset reason | Extra diagnostics, disabled by default. |

Controls require the device admin key. Monitoring works without it.

PCM encryption is read-only here. Enabling encryption requires coordinated key
staging, bridge enrollment, verification, and activation. Use the StreamLine
device and bridge consoles for that workflow.

Firmware installation uses the device's guarded OTA path. The ESP32 downloads
the release, verifies its checksum, writes the inactive application slot, and
reboots only after verification. Home Assistant never handles the image or the
device credential.

## Requirements

- Home Assistant 2026.7 or newer
- ESP32 StreamLine firmware 0.6.1 or newer
- Network access from Home Assistant to the device HTTP API
- The device admin key for controls and firmware management

## Install

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/lutyjj/esp32-streamline-hacs` as an **Integration**.
3. Download **ESP32 StreamLine** and restart Home Assistant when HACS asks.
4. Open **Settings → Devices & services → Add integration** and choose
   **ESP32 StreamLine**.
5. Enter the ESP32 root URL, such as `http://192.0.2.1`, and its admin key.

Use **Reconfigure** on the integration entry to change the URL or admin key.

## Develop

All checks run in Docker:

```sh
make check
```

`custom_components/streamline/models.py` is generated from the device OpenAPI
contract pinned in the Makefile. Advance that pin when the integration requires
a newer firmware contract, then regenerate the models:

```sh
make generate
```

CI fails when generated models, supported operations, translations, or client
request behavior drift from the pinned contract. A scheduled job checks the
StreamLine `mainline` contract as an early warning without changing or releasing
either repository.

## Release

[release-please](https://github.com/googleapis/release-please) maintains a
release PR from the Conventional Commits on `mainline`. It bumps the
`manifest.json` version and prepends `CHANGELOG.md`; merging the PR creates the
`vX.Y.Z` tag and a draft GitHub Release. Publication then verifies the tagged
tree, publishes the release, and validates it with HACS. Land a Conventional
Commit and let the release PR carry the version, never edit `manifest.json` or
`CHANGELOG.md` by hand.

HACS reads the manifest version and published GitHub tags for updates, and
shows the GitHub Release body as the update announcement in Home Assistant. That
body lists user-facing changes (`feat`, `fix`, `perf`); maintenance, CI, and
dependency commits stay out.

## License

[GPL-3.0](LICENSE)

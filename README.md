# ESP32 StreamLine for Home Assistant

[![CI](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml)
[![HACS](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml)

This HACS integration connects Home Assistant to an [ESP32 StreamLine](https://github.com/lutyjj/esp32-streamline) bridge. It creates one device per audio source with these entities:

- Audio streaming state
- Peak audio level
- Listener count
- Lost packet count, disabled by default
- Recording switch when the bridge has storage and an API token

The integration polls the bridge locally every five seconds. It sends no data to cloud services.

## Requirements

- Home Assistant 2026.7 or newer
- ESP32 StreamLine bridge 0.6.1 or newer
- Network access from Home Assistant to the bridge HTTP port
- The bridge API token for recording control; monitoring works without it

## Install

1. Open HACS, select **Custom repositories**, and add `https://github.com/lutyjj/esp32-streamline-hacs` as an **Integration**.
2. Download **ESP32 StreamLine** and restart Home Assistant when HACS asks.
3. Open **Settings → Devices & services → Add integration** and choose **ESP32 StreamLine**.
4. Enter the bridge root URL, such as `http://192.0.2.1:8088`. Add the bridge API token to enable recording control.

Use **Reconfigure** on the integration entry to change the bridge URL or token.

## Develop

All checks run in Docker:

```sh
make check
```

`custom_components/streamline/models.py` is generated from the bridge OpenAPI schemas on the StreamLine `mainline` branch. Regenerate it after a bridge contract change:

```sh
make generate
```

CI fetches the same contract and fails when the generated models or the client's method, path, or authentication behavior drift from it.

## License

[MIT](LICENSE)

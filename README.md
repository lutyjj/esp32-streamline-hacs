# ESP32 StreamLine for Home Assistant

[![CI](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/ci.yml)
[![HACS](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml/badge.svg?branch=mainline)](https://github.com/lutyjj/esp32-streamline-hacs/actions/workflows/validate.yml)

This HACS integration connects Home Assistant directly to an [ESP32 StreamLine](https://github.com/lutyjj/esp32-streamline) device. Each ESP32 appears as one Home Assistant device with these entities:

- Playback state, peak audio level, Wi-Fi signal, and health
- Network error count, disabled by default
- Input selector, input gain, and ADC attenuation
- Analog passthrough when the selected board supports it

The integration polls the ESP32 locally every five seconds. It sends no data to cloud services. Bridge-hosted playback and recordings remain owned by the separate StreamLine bridge.

## Requirements

- Home Assistant 2026.7 or newer
- ESP32 StreamLine firmware 0.6.1 or newer
- Network access from Home Assistant to the device HTTP API
- The device admin key for controls; monitoring works without it

## Install

1. Open HACS, select **Custom repositories**, and add `https://github.com/lutyjj/esp32-streamline-hacs` as an **Integration**.
2. Download **ESP32 StreamLine** and restart Home Assistant when HACS asks.
3. Open **Settings → Devices & services → Add integration** and choose **ESP32 StreamLine**.
4. Enter the ESP32 root URL, such as `http://192.0.2.1`. Add its admin key to enable controls.

Use **Reconfigure** on the integration entry to change the device URL or admin key.

## Develop

All checks run in Docker:

```sh
make check
```

`custom_components/streamline/models.py` is generated from the device OpenAPI schemas on the StreamLine `mainline` branch. Regenerate it after a device contract change:

```sh
make generate
```

CI fetches the same contract and fails when the generated models or the client's method, path, or authentication behavior drift from it.

## License

[GPL-3.0](LICENSE)

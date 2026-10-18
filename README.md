# PiRowFlo Control API

Small FastAPI-based control API for the SmartRow-focused
[PiRowFlo](https://github.com/stampede79/pirowflo) setup.

The API provides an HTTP interface between the
[PiRowFlo Control App](https://github.com/stampede79/pirowflo-control-app)
and the PiRowFlo processes managed by Supervisor.

> **Note**
>
> The current API controls the SmartRow profiles of PiRowFlo.
> WaterRower S4 profiles are not currently exposed through this API.

## Architecture

```text
PiRowFlo Control App
        |
        | HTTP / REST
        | X-API-Key
        v
PiRowFlo Control API
        |
        +---- Supervisor
        |       |
        |       +---- SmartRow + BLE + ANT+
        |       +---- SmartRow + BLE
        |       +---- SmartRow + ANT+
        |
        +---- PiRowFlo control socket
        |
        v
     PiRowFlo
```

## Features

The API provides functionality for:

- retrieving the current PiRowFlo process status
- retrieving the SmartRow Bluetooth connection status
- starting PiRowFlo in Bluetooth + ANT+ mode
- starting PiRowFlo in Bluetooth-only mode
- starting PiRowFlo in ANT+-only mode
- stopping PiRowFlo
- restarting PiRowFlo
- resetting the current SmartRow/PiRowFlo session

## Installation

For a complete PiRowFlo installation, use the dedicated installer:

https://github.com/stampede79/pirowflo-installer

The installer installs both PiRowFlo and this Control API and creates the
required systemd configuration.

The default installation directory is:

```text
/opt/pirowflo-control-api
```

## Manual setup

Create a Python virtual environment:

```bash
python3 -m venv venv
```

Install the dependencies:

```bash
venv/bin/pip install -r requirements.txt
```

The API currently requires:

- FastAPI
- Uvicorn

## Configuration

Configuration is provided through environment variables.

A typical installation uses:

```text
/etc/pirowflo-control.env
```

Example:

```text
PIROWFLO_API_KEY=<secret>
PIROWFLO_SUPERVISORCTL=/opt/pirowflo/venv/bin/supervisorctl
PIROWFLO_SUPERVISOR_CONFIG=/opt/pirowflo/services/supervisord.conf
PIROWFLO_CONTROL_SOCKET=/tmp/pirowflo-control.sock
```

Do not commit the API key to Git.

## Authentication

All control and status requests require an API key.

The client sends the key using the HTTP header:

```text
X-API-Key: <secret>
```

The installer automatically generates an API key.

On the PiRowFlo host, the configured key can be displayed with:

```bash
sudo grep '^PIROWFLO_API_KEY=' /etc/pirowflo-control.env
```

Keep this key private.

## Running the API

The production installation uses systemd.

Check the service:

```bash
systemctl status pirowflo-control.service
```

The API listens on:

```text
0.0.0.0:8090
```

For manual testing:

```bash
PIROWFLO_API_KEY=test \
PIROWFLO_SUPERVISORCTL=/opt/pirowflo/venv/bin/supervisorctl \
PIROWFLO_SUPERVISOR_CONFIG=/opt/pirowflo/services/supervisord.conf \
PIROWFLO_CONTROL_SOCKET=/tmp/pirowflo-control.sock \
venv/bin/uvicorn app:app --host 0.0.0.0 --port 8090
```

## SmartRow profiles

The API currently maps the available modes to these PiRowFlo Supervisor
processes:

```text
combined
    -> pirowflo_SR_SmartRow_Bluetooth_AntPlus

bluetooth
    -> pirowflo_SR_Smartrow_Bluetooth_only

ant
    -> pirowflo_SR_Smartrow_AntPlus_only
```

These profiles are SmartRow-specific.

The S4 profiles inherited from the original PiRowFlo project are not currently
exposed by the Control API.

## Status

The API reports both:

- the state of the PiRowFlo Supervisor profiles
- the SmartRow Bluetooth connection state

This allows clients to distinguish between a running PiRowFlo process and an
actually connected SmartRow.

## Testing with curl

First load the API key:

```bash
API_KEY=$(sudo sed -n 's/^PIROWFLO_API_KEY=//p' \
  /etc/pirowflo-control.env)
```

Request the current status:

```bash
curl \
  -H "X-API-Key: $API_KEY" \
  http://127.0.0.1:8090/api/status
```

A successful response contains the PiRowFlo profile states and SmartRow
connection information.

## Logs

View the API service log with:

```bash
journalctl -u pirowflo-control.service
```

Follow it in real time:

```bash
journalctl -u pirowflo-control.service -f
```

## Related projects

- [PiRowFlo](https://github.com/stampede79/pirowflo)
- [PiRowFlo Control App](https://github.com/stampede79/pirowflo-control-app)
- [PiRowFlo Installer](https://github.com/stampede79/pirowflo-installer)

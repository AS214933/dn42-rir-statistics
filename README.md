# DN42 RIR statistics

Generate and serve DN42 registry snapshots in the RIR statistics exchange
format. The project treats each object `source` value from the DN42 registry as
a registry and publishes files under `/stats/<registry>/`.

The default registry source is the public Origami mirror:

```text
https://git.origami.pub/Bingxin/dn42-registry.git
```

The generated output follows the APNIC RIR statistics exchange format where it
fits DN42 data:

- `delegated-<registry>-yyyymmdd`
- `delegated-<registry>-latest`
- matching `.md5` checksum files
- `version|registry|serial|records|startdate|enddate|utcoffset`
- `registry|*|type|*|count|summary`
- `registry|cc|type|start|value|date|status`

All generated file names and file contents are lowercase.

## Install

The code uses only the Python standard library. Python 3.11 or newer is
recommended.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Generate once

This clones or updates the DN42 registry into `.cache/dn42-registry` and writes
output to `public/stats`.

```sh
dn42-rir-statistics generate --output-dir public
```

Use a local registry checkout instead:

```sh
dn42-rir-statistics generate --registry-dir /path/to/dn42-registry --output-dir public
```

Validate generated files:

```sh
dn42-rir-statistics validate --output-dir public
```

## Serve HTTP

The HTTP server publishes `public` as the document root, so statistics are
available below `/stats/<registry>/`.

```sh
dn42-rir-statistics web --output-dir public --host 0.0.0.0 --port 8000
```

Example URL:

```text
http://127.0.0.1:8000/stats/dn42/delegated-dn42-latest
```

## Serve rsync

The rsync command starts a read-only rsync daemon with a `stats` module pointing
at `public/stats`. It requires the system `rsync` binary.

```sh
dn42-rir-statistics rsync --output-dir public --host 0.0.0.0 --port 8730
```

Example client command:

```sh
rsync rsync://127.0.0.1:8730/stats/dn42/delegated-dn42-latest .
```

## Daily server

The combined server generates at startup, starts HTTP and rsync, and regenerates
once per day at the configured UTC time.

```sh
dn42-rir-statistics serve \
  --output-dir public \
  --web-host 0.0.0.0 \
  --web-port 8000 \
  --rsync-host 0.0.0.0 \
  --rsync-port 8730 \
  --daily-at 03:00
```

Disable rsync when the binary is not installed:

```sh
dn42-rir-statistics serve --no-rsync
```

## References

- APNIC RIR statistics exchange format:
  <https://www.apnic.net/about-apnic/corporate-documents/documents/resource-guidelines/rir-statistics-exchange-format/>
- DN42 registry mirror:
  <https://git.origami.pub/Bingxin/dn42-registry>

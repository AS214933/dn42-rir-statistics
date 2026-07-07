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

## Docker

Build the image locally:

```sh
docker build -t dn42-rir-statistics:local .
```

Run the combined daily server:

```sh
docker run --rm \
  --name dn42-rir-statistics \
  -p 8000:8000 \
  -p 8730:8730 \
  -v dn42-rir-data:/data \
  dn42-rir-statistics:local
```

The container stores generated files and the DN42 registry cache under `/data`.
By default it runs:

```sh
dn42-rir-statistics serve \
  --output-dir /data/public \
  --cache-dir /data/cache/dn42-registry \
  --web-host 0.0.0.0 \
  --web-port 8000 \
  --rsync-host 0.0.0.0 \
  --rsync-port 8730 \
  --rsync-config /data/rsyncd.conf \
  --daily-at 03:00
```

Override the command to change ports, schedule, or source registry:

```sh
docker run --rm -p 8080:8080 -v dn42-rir-data:/data dn42-rir-statistics:local \
  serve \
  --output-dir /data/public \
  --cache-dir /data/cache/dn42-registry \
  --web-host 0.0.0.0 \
  --web-port 8080 \
  --rsync-host 0.0.0.0 \
  --rsync-port 8730 \
  --rsync-config /data/rsyncd.conf \
  --daily-at 06:00
```

## Docker Compose

The included `compose.yaml` is a local example. Update the `image` value before
using it as a published deployment reference.

```sh
docker compose up -d --build
```

Generated files are available at:

```text
http://127.0.0.1:8000/stats/dn42/delegated-dn42-latest
rsync://127.0.0.1:8730/stats/dn42/delegated-dn42-latest
```

## GitHub Container Registry

The workflow in `.github/workflows/container.yml` builds multi-architecture
images for `linux/amd64` and `linux/arm64`, then pushes them to GHCR on pushes
to `main`, `master`, tags matching `v*`, and manual runs. Pull requests build
the image without pushing it.

The published image name is derived from the repository name and lowercased:

```text
ghcr.io/<owner>/<repository>
```

Repository settings must allow GitHub Actions to write packages. The workflow
uses the built-in `GITHUB_TOKEN`; no separate registry token is required for
normal same-repository GHCR publishing.

## References

- APNIC RIR statistics exchange format:
  <https://www.apnic.net/about-apnic/corporate-documents/documents/resource-guidelines/rir-statistics-exchange-format/>
- DN42 registry mirror:
  <https://git.origami.pub/Bingxin/dn42-registry>

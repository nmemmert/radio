# AzuraCast (self-hosted radio automation)

Full-featured alternative to the hand-built `icecast`/`liquidsoap` stack in the rest of this
repo — playlists, scheduling, live DJ broadcasting, and a web UI, all built on the same
Icecast/Liquidsoap engine, bundled into one official image
(`ghcr.io/azuracast/azuracast`). No custom Dockerfiles or GitHub Actions needed here; this is
just the official upstream image, reformatted into ZimaOS/CasaOS custom-install style.

## Before installing

Edit these placeholders in `docker-compose.yml`:

- `MYSQL_PASSWORD` — set to a random value (internal DB password, never exposed externally).
- The last `volumes` entry's `source` — your existing music library path (defaults to the same
  path used by the old stack: `/media/Plex/Media/Music/Shared Music`).
- The last `volumes` entry's `target` — must be
  `/var/azuracast/stations/<your-station-shortcode>/media/library`. Defaults to `home_radio`
  (matching the station already created); update this if you rename or recreate the station with
  a different URL stub. See "Importing your library" below for why this path matters.

Everything else (bind-mount paths under `/DATA/AppData/azuracast/...`, the station port range)
can be left as-is.

## Why the ports are shifted to 9000-9496

The old `icecast` container still publishes host port `8000` during the transition period. To
avoid a collision, this compose file shifts AzuraCast's entire auto-assigned station port range
up by 1000 (the official default is `8000-8499`; this uses `9000-9499`). Once the old stack is
decommissioned, this can be changed back if you want, but there's no need to.

## Why there's no `updater` service

The official compose file also includes an `azuracast_updater` container that mounts
`/var/run/docker.sock` to auto-update AzuraCast. That grants a container root-equivalent control
over the whole Docker daemon, which is a meaningfully bigger privilege than anything else in this
project takes on. Left out by default — update manually by pulling a newer image tag when you
want to. Add it back yourself if you'd rather have auto-updates and accept that tradeoff.

## Installing

Paste `docker-compose.yml`'s contents (with your edits) into ZimaOS's custom-install /
compose-import screen, or run `docker compose up -d` from this folder over SSH.

Since `radio.necloud.us` currently points at the old stack, set up a **temporary** subdomain in
Nginx Proxy Manager for initial testing — e.g. `azuracast.necloud.us` → `<zimaos-lan-ip>:8080`,
SSL via Let's Encrypt as usual. Once you've created a station and confirmed it's streaming, you
can repoint (or add) `radio.necloud.us` to AzuraCast and decommission the old `icecast`/
`liquidsoap` containers.

## Importing your library

**Do not point a station's "Media Storage Location" or "Base Station Directory" directly at your
external library.** AzuraCast treats whatever's configured there as content it fully owns and
manages — including deleting files it doesn't recognize. During testing, setting a station's
"Base Station Directory" to a mounted external path caused AzuraCast to attempt to `unlink()` a
real song file as a "cleanup" side effect. It only failed because of a permissions mismatch —
with matching permissions, that file would have been deleted.

The safe, officially-documented pattern instead: leave the station's Media Storage Location on
its default (a subfolder under `/var/azuracast/stations/<shortcode>/media`, which AzuraCast owns
and is free to manage), and bind-mount your real library **read-only** as a subfolder *inside*
that same default media folder — that's exactly what this compose file's last volume entry does
(`.../media/library`, `read_only: true`). AzuraCast scans it as part of the station's existing
media location automatically; no separate Storage Location needs to be created. Because the
mount itself is read-only at the OS level, it is physically impossible for AzuraCast to modify or
delete anything in your real library, regardless of what its internal logic tries to do.

The one tradeoff: AzuraCast can't write updated metadata/album art back to files under a
read-only mount (it'll just save those to its own database instead, per AzuraCast's docs) — a
reasonable price for guaranteed safety of the only copy of your library.

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
  path used by the old stack: `/media/Plex/Media/Music/Shared Music`). This is mounted **read
  only** at `/var/azuracast/library` for reference/import — it is *not* automatically a station's
  live media folder. See "Importing your library" below.

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

Your existing library is mounted read-only at `/var/azuracast/library` inside the container so
it's visible without copying anything yet. How to actually get AzuraCast playing from it depends
on what you decide once you've created a station in the UI:

- Each station has its own media folder under `/var/azuracast/stations/<shortcode>/media`
  (already bind-mounted to `/DATA/AppData/azuracast/stations` on the host). You could symlink
  or copy from `/var/azuracast/library` into there.
- AzuraCast may also support a custom absolute storage location per station (under
  Administration → Storage Locations) pointing directly at a mounted path, avoiding a copy
  entirely — worth checking in the UI before copying anything.

This part hasn't been tested yet — treat it as the first thing to figure out once the base app
is up and you've created your first station.

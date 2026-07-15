# Personal Internet Radio

Streams your music library as a single continuous, shuffled Icecast stream — like a real radio
station that anyone can tune into. Built with:

- **Liquidsoap** — shuffles your library, crossfades between tracks, and feeds a continuous stream
  to Icecast. Reads artist/title from ID3 tags. Optionally pulls your podcast RSS feed and airs
  episodes on a daily schedule.
- **Icecast** — serves that stream to listeners at a public mount point.
- **Nginx Proxy Manager (NPM)** — terminates HTTPS and proxies your domain to Icecast (assumed
  already running on your ZimaOS box).
- **Web player** (`icecast/web/player.html`) — self-contained page served at the site root.
  Play/pause, skip (password-protected), volume, live "now playing" with separate artist/title,
  listener count, and a "recently played" history — all polled from Icecast's `/status-json.xsl`,
  no extra backend needed.

Listeners can just hit `https://radio.yourdomain.com/` for the player, or use the raw stream URL
directly in VLC, phone radio apps, etc.

## How images get to ZimaOS

Neither image is built on the ZimaOS box. A GitHub Actions workflow
(`.github/workflows/build.yml`) builds both `icecast/` and `liquidsoap/` (the Liquidsoap script
is baked into its image at build time) and pushes them to GitHub Container Registry
(`ghcr.io/nmemmert/radio-icecast`, `ghcr.io/nmemmert/radio-liquidsoap`) on every push to `main`
that touches either folder.

`docker-compose.yml` is a self-contained ZimaOS/CasaOS-style app definition (same shape as your
Emby app) — it references those pre-built images directly and needs no `.env` file. **ZimaOS
doesn't need this git repo at all**: just take the contents of `docker-compose.yml`, edit the
placeholder values, and paste it into ZimaOS's "Install a customized app" / compose-import screen
(or drop it in a folder and run `docker compose up -d` over SSH if you prefer the CLI).

**One-time step after the first successful workflow run:** by default GHCR publishes new
packages as private, even from a public push. Go to the repo on GitHub → **Packages** (right
sidebar) → for each of `radio-icecast` and `radio-liquidsoap` → **Package settings** → change
visibility to **Public**. This lets ZimaOS pull without any registry login. (Neither image has
secrets baked in — passwords/paths are just plain environment values — so public is safe.)

## Networking note

Unlike a single-container app (e.g. Emby), `icecast` and `liquidsoap` need to talk to each
other. Rather than rely on Docker's DNS-based service discovery (ZimaOS's app install flow may
not set up the same kind of network a plain `docker compose up` would), `liquidsoap` uses
`network_mode: "service:icecast"` — it literally shares icecast's network namespace and talks to
it over `localhost:8000`, no name resolution involved. Only `icecast` publishes a port to the
host (`8000`), the same way Emby publishes `8096`/`8920`. Point your reverse proxy at
`<zimaos-lan-ip>:8000`, not at a container name.

## One-time setup

### 1. Edit the placeholder values

Before installing, edit these in `docker-compose.yml`:

- `icecast.environment`:
  - `ICECAST_HOSTNAME` — your public subdomain (e.g. `radio.yourdomain.com`).
  - `ICECAST_SOURCE_PASSWORD` — generate a strong value (e.g. `openssl rand -hex 16`). **Must
    match** the `liquidsoap` service's `ICECAST_SOURCE_PASSWORD` below it.
  - `ICECAST_RELAY_PASSWORD` — any random value (unused unless you add a relay).
  - `ICECAST_ADMIN_USER` / `ICECAST_ADMIN_PASSWORD` — credentials for the Icecast admin panel.
- `liquidsoap.environment.ICECAST_SOURCE_PASSWORD` — same value as icecast's above.
- `liquidsoap.environment.PODCAST_FEED_URL` *(optional)* — the RSS feed URL for your podcast.
  When set, Liquidsoap will pull episode enclosures from the feed and play them during the
  scheduled window. Leave blank to keep music-only.
- `liquidsoap.environment.PODCAST_TIME` *(optional)* — Liquidsoap time predicate for when to air
  podcast episodes, e.g. `8h-9h` plays them 8–9am every day. Leave blank to disable.
- `liquidsoap.volumes[0].source` — absolute path on the ZimaOS host to your music library
  (default placeholder: `/DATA/Media/Music`). Mixed mp3/flac/etc is fine.

Don't commit your real passwords back into this file in the repo — keep the checked-in version
with placeholders and only fill in real values in the copy you install on ZimaOS.

### 2. Install on ZimaOS

Paste the edited YAML into ZimaOS's custom-install/compose-import screen, or place it at e.g.
`/DATA/AppData/radio/docker-compose.yml` and run:

```sh
docker compose pull
docker compose up -d
```

Check logs:

```sh
docker compose logs -f liquidsoap
```

You should see it connect to Icecast without repeated errors.

### 3. Add the proxy host in Nginx Proxy Manager

In the NPM UI, add a new **Proxy Host**:

- Domain: your chosen subdomain (e.g. `radio.yourdomain.com`)
- Scheme: `http`, Forward Hostname/Port: `<zimaos-lan-ip>` / `8000`
- SSL tab: request a new Let's Encrypt certificate, force SSL
- **Advanced** tab, add this custom Nginx config so the live stream isn't buffered/delayed:

  ```
  proxy_buffering off;
  ```

Save. It should immediately be reachable at `https://radio.yourdomain.com`.

## Verification

1. `docker compose logs -f liquidsoap` — confirms a clean connection to Icecast.
2. Visit `https://radio.yourdomain.com/` — the web player should load, show "Live" with a
   listener count, and display the currently playing track.
3. Visit `https://radio.yourdomain.com/status.xsl` — Icecast's raw status page (still reachable
   directly, just no longer the site root) should show the `/stream` mountpoint.
4. Press play on the web player, or open `https://radio.yourdomain.com/stream` directly in VLC —
   audio should play continuously, with metadata updating as tracks change.
5. `docker compose restart liquidsoap` — confirms it reconnects automatically and playback
   resumes (validates resilience after a reboot/crash).

## Updating the stack

New pushes to `main` rebuild the images automatically. On ZimaOS, just re-pull and recreate:

```sh
docker compose pull
docker compose up -d
```

If `docker-compose.yml` itself changes, update the installed copy on ZimaOS to match before
running the above.

## Updating the library

Just add/remove files under the music path on the ZimaOS host — Liquidsoap watches the directory
and picks up changes automatically (no restart needed).

## Admin access

Icecast's admin panel is at `https://radio.yourdomain.com/admin/` using the
`ICECAST_ADMIN_USER` / `ICECAST_ADMIN_PASSWORD` values you set.

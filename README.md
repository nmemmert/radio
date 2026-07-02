# Personal Internet Radio

Streams your music library as a single continuous, shuffled Icecast stream — like a real radio
station that anyone can tune into. Built with:

- **Liquidsoap** — shuffles your library with crossfades and feeds a continuous stream to Icecast.
- **Icecast** — serves that stream to listeners at a public mount point.
- **Nginx Proxy Manager (NPM)** — terminates HTTPS and proxies your domain to Icecast (assumed
  already running on your ZimaOS box).

Listeners connect directly to the stream URL (VLC, browsers via `<audio>`, phone radio apps,
etc). A custom web player page is a future step, not included here.

## How images get to ZimaOS

The `icecast` image isn't built on the ZimaOS box. A GitHub Actions workflow
(`.github/workflows/build.yml`) builds it from `icecast/` and pushes it to GitHub Container
Registry (`ghcr.io/nmemmert/radio-icecast`) on every push to `main` that touches `icecast/`.
`docker-compose.yml` just references that image, so deploying/updating on ZimaOS is a `git pull`
+ `docker compose pull` + `docker compose up -d` — no build tools or CPU-heavy image builds on
the device itself. `liquidsoap` already uses the official pre-built `savonet/liquidsoap` image.

**One-time step after the first successful workflow run:** by default GHCR publishes new
packages as private, even from a public push. Go to the repo on GitHub → **Packages** (right
sidebar) → `radio-icecast` → **Package settings** → change visibility to **Public**. This lets
ZimaOS `docker compose pull` without needing any registry login. (The image itself has no
secrets baked in — passwords are injected from `.env` at container start — so public is safe.)

## One-time setup

### 1. Find your NPM Docker network name

On the ZimaOS box:

```sh
docker network ls
```

Look for the network NPM's container is attached to (often something like `npm_default` or
`nginxproxymanager_default`). You'll need this for `.env`.

### 2. Clone and configure

```sh
git clone <this-repo-url> radio
cd radio
cp .env.example .env
```

Edit `.env`:

- `ICECAST_HOSTNAME` — the public subdomain you'll use (e.g. `radio.yourdomain.com`).
- `ICECAST_SOURCE_PASSWORD`, `ICECAST_RELAY_PASSWORD`, `ICECAST_ADMIN_PASSWORD` — generate
  strong random values, e.g. `openssl rand -hex 16` for each.
- `MUSIC_DIR` — absolute path on the ZimaOS host to your music folder (mixed mp3/flac/etc is
  fine).
- `NPM_NETWORK` — the network name found in step 1.

### 3. Start it

```sh
docker compose pull
docker compose up -d
```

Check logs:

```sh
docker compose logs -f liquidsoap
```

You should see it connect to Icecast without repeated errors.

### 4. Add the proxy host in Nginx Proxy Manager

In the NPM UI, add a new **Proxy Host**:

- Domain: your chosen subdomain (e.g. `radio.yourdomain.com`)
- Scheme: `http`, Forward Hostname/Port: `icecast` / `8000`
- Enable **Websockets Support** (harmless either way, not strictly required for Icecast)
- SSL tab: request a new Let's Encrypt certificate, force SSL
- **Advanced** tab, add this custom Nginx config so the live stream isn't buffered/delayed:

  ```
  proxy_buffering off;
  ```

Save. It should immediately be reachable at `https://radio.yourdomain.com`.

## Verification

1. `docker compose logs -f liquidsoap` — confirms a clean connection to Icecast.
2. Visit `https://radio.yourdomain.com/status.xsl` — Icecast's status page should show the
   `/stream` mountpoint, current listener count, and the currently playing track.
3. Open `https://radio.yourdomain.com/stream` in VLC or a browser — audio should play
   continuously, with metadata updating as tracks change.
4. `docker compose restart liquidsoap` — confirms it reconnects automatically and playback
   resumes (validates resilience after a reboot/crash).

## Updating the stack

Pull the latest code and images, then recreate containers:

```sh
git pull
docker compose pull
docker compose up -d
```

## Updating the library

Just add/remove files under `MUSIC_DIR` on the ZimaOS host — Liquidsoap watches the directory
and picks up changes automatically (no restart needed).

## Admin access

Icecast's admin panel is at `https://radio.yourdomain.com/admin/` using `ICECAST_ADMIN_USER` /
`ICECAST_ADMIN_PASSWORD` from your `.env`.

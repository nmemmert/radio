#!/bin/sh
# Source admin-saved settings before building the script.
[ -f /config/settings.env ] && . /config/settings.env

PODCAST_FEED_URL="${PODCAST_FEED_URL:-}"
PODCAST_TIME="${PODCAST_TIME:-}"

# Assemble /tmp/radio.liq from pre + generated switch cases + post.
{
  cat /tmp/radio_pre.liq

  # Scheduled custom playlists from /config/schedule.json
  # Format: [{"name":"...","file":"...","time":"8h-10h"}, ...]
  if [ -f /config/schedule.json ]; then
    grep -o '{[^}]*}' /config/schedule.json | while IFS= read -r obj; do
      ptime=$(printf '%s' "$obj" | grep -o '"time":"[^"]*"' | cut -d'"' -f4)
      pfile=$(printf '%s' "$obj" | grep -o '"file":"[^"]*"' | cut -d'"' -f4)
      if [ -n "$ptime" ] && [ -n "$pfile" ]; then
        printf '  ({ %s }, playlist(mode="randomize", reload_mode="watch", "%s")),\n' "$ptime" "$pfile"
      fi
    done
  fi

  # Podcast block (if both feed URL and time window are configured)
  if [ -n "$PODCAST_FEED_URL" ] && [ -n "$PODCAST_TIME" ]; then
    printf '  ({ %s }, podcast),\n' "$PODCAST_TIME"
  fi

  cat /tmp/radio_post.liq
} > /tmp/radio.liq

# Ensure config dir and history.log exist so file.write(append=true) doesn't fail on first track.
mkdir -p /config
touch /config/history.log

exec liquidsoap /tmp/radio.liq

#!/usr/bin/liquidsoap

settings.log.stdout.set(true)
settings.log.level.set(3)

icecast_host    = "localhost"
icecast_port    = 8000
source_password = environment.get("ICECAST_SOURCE_PASSWORD")

# Station identity — set via admin panel or env vars in docker-compose.
station_name    = environment.get("STATION_NAME",        default="My Radio")
station_desc    = environment.get("STATION_DESCRIPTION", default="Personal music stream")
genre           = environment.get("GENRE",               default="Various")
crossfade_secs  = float_of_string(default=3.0, environment.get("CROSSFADE_DURATION", default="3"))

podcast_feed    = environment.get("PODCAST_FEED_URL", default="")
podcast_time    = environment.get("PODCAST_TIME",     default="")

# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

music_raw = playlist(id="music", mode="randomize", reload_mode="watch", "/music")

# Pull clean artist/title from ID3 tags; fall back to stripping the filename.
def clean_meta(m) =
  title  = m["title"]
  artist = m["artist"]
  fname  = m["filename"]

  title =
    if title == "" then
      base = list.last(default="", string.split(separator="/", fname))
      fst(default=base, string.split(separator=".", base))
    else
      title
    end

  [("title", title), ("artist", artist),
   ("album", m["album"]), ("filename", fname)]
end

music = map_metadata(clean_meta, music_raw)

music =
  if crossfade_secs > 0.0 then
    crossfade(duration=crossfade_secs, fade_out=crossfade_secs, fade_in=crossfade_secs, music)
  else
    music
  end

# ---------------------------------------------------------------------------
# Podcast (optional)
# ---------------------------------------------------------------------------

has_podcast = podcast_feed != ""

podcast =
  if has_podcast then
    playlist(mode="normal", reload_mode="watch", podcast_feed)
  else
    blank()
  end

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

radio =
  if has_podcast and podcast_time != "" then
    switch(track_sensitive=false, [
      ({ (podcast_time) }, podcast),
      ({ true }, music)
    ])
  else
    music
  end

radio = fallback(track_sensitive=false, [radio, blank(duration=5.)])

# ---------------------------------------------------------------------------
# Telnet — used by the admin panel for skip
# ---------------------------------------------------------------------------

settings.server.telnet.set(true)
settings.server.telnet.bind_addr.set("127.0.0.1")
settings.server.telnet.port.set(1234)

# ---------------------------------------------------------------------------
# History — written to shared /config volume so the admin panel can read it
# ---------------------------------------------------------------------------

def on_track_change(m) =
  artist = m["artist"]
  title  = m["title"]
  ts     = time.to_string(time.utc(time()))
  ignore(file.write(append=true, "/config/history.log", "#{ts} | #{artist} | #{title}\n"))
end

radio.on_track(on_track_change)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

output.icecast(
  %mp3(bitrate=192),
  host=icecast_host,
  port=icecast_port,
  password=source_password,
  mount="/stream",
  name=station_name,
  description=station_desc,
  genre=genre,
  radio
)

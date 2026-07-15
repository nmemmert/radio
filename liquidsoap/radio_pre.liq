#!/usr/bin/liquidsoap

settings.log.stdout.set(true)
settings.log.level.set(3)

icecast_host    = "localhost"
icecast_port    = 8000
source_password = environment.get("ICECAST_SOURCE_PASSWORD")
station_name    = environment.get("STATION_NAME",        default="My Radio")
station_desc    = environment.get("STATION_DESCRIPTION", default="Personal music stream")
genre           = environment.get("GENRE",               default="Various")
crossfade_secs  = float_of_string(default=3.0, environment.get("CROSSFADE_DURATION", default="3"))
podcast_feed    = environment.get("PODCAST_FEED_URL", default="")

music_raw = playlist(id="music", mode="randomize", reload_mode="watch", "/music")

def clean_meta(m) =
  title  = m["title"]
  artist = m["artist"]
  fname  = m["filename"]
  title =
    if title == "" then
      base = list.last(default="", string.split(separator="/", fname))
      list.hd(default=base, string.split(separator=".", base))
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

podcast =
  if podcast_feed != "" then
    playlist(mode="normal", reload_mode="watch", podcast_feed)
  else
    blank()
  end

# Switch cases for scheduled playlists and podcast are injected here by entrypoint.sh.
radio = switch(track_sensitive=false, [

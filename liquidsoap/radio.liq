#!/usr/bin/liquidsoap

settings.log.stdout.set(true)
settings.log.level.set(3)

icecast_host = "icecast"
icecast_port = 8000
source_password = environment.get("ICECAST_SOURCE_PASSWORD")

# Recursively scans /music, shuffles on each full pass, and picks up new/
# removed files without a restart.
music = playlist(mode="randomize", reload_mode="watch", "/music")

# Silence fallback so the stream never dies if the library is briefly empty.
radio = fallback(track_sensitive=false, [music, blank(duration=5.)])

def transition(a, b) =
  cross.smart(a, b)
end
radio = cross(duration=3., transition, radio)

output.icecast(
  %mp3(bitrate=192),
  host=icecast_host,
  port=icecast_port,
  password=source_password,
  mount="/stream",
  name="My Radio",
  description="Personal music stream",
  genre="Various",
  radio
)

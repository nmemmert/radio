  ({true}, music)
])

radio = fallback(track_sensitive=false, [radio, blank(duration=5.)])

settings.server.telnet.set(true)
settings.server.telnet.bind_addr.set("127.0.0.1")
settings.server.telnet.port.set(1234)

def on_track_change(m) =
  artist = m["artist"]
  title  = m["title"]
  ts     = time.to_string(time.utc(time()))
  ignore(file.write(append=true, "/config/history.log", "#{ts} | #{artist} | #{title}\n"))
end

radio.on_track(on_track_change)

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

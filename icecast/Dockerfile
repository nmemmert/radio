FROM alpine:3.20

RUN apk add --no-cache icecast gettext

COPY icecast.xml.template /etc/icecast.xml.template
COPY entrypoint.sh /entrypoint.sh
COPY web/player.html /usr/share/icecast/web/player.html
RUN chmod +x /entrypoint.sh

USER icecast

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

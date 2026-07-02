FROM alpine:3.20

RUN apk add --no-cache icecast gettext \
    && adduser -D -H -s /sbin/nologin icecast

COPY icecast.xml.template /etc/icecast.xml.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER icecast

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

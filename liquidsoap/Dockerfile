FROM savonet/liquidsoap:v2.4.5

COPY radio.liq /tmp/radio.liq
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

FROM savonet/liquidsoap:v2.4.5

COPY radio.liq /tmp/radio.liq
COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

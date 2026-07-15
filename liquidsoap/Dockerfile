FROM savonet/liquidsoap:v2.4.5

COPY --chmod=755 entrypoint.sh /entrypoint.sh
COPY radio_pre.liq  /tmp/radio_pre.liq
COPY radio_post.liq /tmp/radio_post.liq

ENTRYPOINT ["/entrypoint.sh"]

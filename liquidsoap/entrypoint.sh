#!/bin/sh
# Source saved settings before starting Liquidsoap so admin panel changes take effect on restart.
[ -f /config/settings.env ] && . /config/settings.env
exec liquidsoap /tmp/radio.liq

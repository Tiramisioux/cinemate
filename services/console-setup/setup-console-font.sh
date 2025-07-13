#!/bin/bash

set -e

echo "[console-setup] Updating /etc/default/console-setup..."
sed -i 's/^FONTFACE=.*/FONTFACE="Terminus"/' /etc/default/console-setup || \
    echo 'FONTFACE="Terminus"' >> /etc/default/console-setup

sed -i 's/^FONTSIZE=.*/FONTSIZE="16x32"/' /etc/default/console-setup || \
    echo 'FONTSIZE="16x32"' >> /etc/default/console-setup

echo "[console-setup] Reconfiguring console-setup..."
dpkg-reconfigure -f noninteractive console-setup

echo "[console-setup] Done."


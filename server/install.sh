#!/bin/bash
# Serverda (root) bir marta: bash install.sh
set -e
D=/opt/avazbek-nashr
mkdir -p $D/.ssh
chown -R botrunner:botrunner $D
chmod 700 $D/.ssh
if [ ! -f $D/.ssh/id_ed25519 ]; then
  sudo -u botrunner ssh-keygen -q -t ed25519 -N "" -C "avazbek-nashr@talim" -f $D/.ssh/id_ed25519
fi
echo "DEPLOY_KEY_PUB: $(cat $D/.ssh/id_ed25519.pub)"

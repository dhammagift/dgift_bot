#!/usr/bin/env bash
# Local/dev setup for the bot: creates a venv named "telegram" (same name the prod
# systemd units under install_sysctl_bots.sh expect, ".../telegram/bin/python"),
# installs deps, and seeds two config files (one bot account is the RU-facing
# @dgift_bot, the other the EN-facing @dhammagift_bot — same code, see main.py's
# WELCOME_MESSAGES/EXTRA_MESSAGES). Fill in the real TOKEN in both before starting.
#
# For a real deployment (systemd services, /var/www/telegram_bot layout), see
# install_sysctl_bots.sh instead — this script is for running the bot locally.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

python3 -m venv telegram
telegram/bin/pip install --upgrade pip -q
telegram/bin/pip install -r requirements.txt -q

for name in dgift_bot dhammagift_bot; do
  target="config.$name.json"
  if [ ! -f "$target" ]; then
    sed "s/dgift_bot/$name/" config.example.json > "$target"
    echo "created $target — fill in a real TOKEN before starting"
  fi
done

cat <<'EOF'

Done. Start a bot with:
  telegram/bin/python main.py config.dgift_bot.json
  telegram/bin/python main.py config.dhammagift_bot.json

sutta_words.txt (autocomplete) and WATCH_DIR degrade gracefully if the dg-node
site (assets/texts/...) isn't deployed alongside this bot — see main.py's
load_words()/watcher.py.
EOF

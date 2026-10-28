#!/usr/bin/env bash
# Detached bizcrax36 poller launcher. `setsid` puts it in its own session so it
# is reparented to init and survives a hermes-gateway restart (s6 --replace).
# A single-instance lock prevents duplicate pollers (getUpdates is exclusive).
set -u
DIR="/opt/data/bizcrax36"
LOCK="$DIR/logs/poller-hermes.lock"
LOG="$DIR/logs/poller-hermes.log"
mkdir -p "$DIR/logs"
# stale-lock check: if the pid in the lock is alive, exit
if [ -f "$LOCK" ]; then
  oldpid="$(cat "$LOCK" 2>/dev/null || true)"
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "$(date -u +%FT%TZ) lock held by $oldpid; exiting" >> "$LOG"
    exit 0
  fi
fi
setsid bash -c "
  set -a; . '$DIR/bizcrax36.env'; set +a;
  export POLL_SECONDS=1;
  echo \$\$ > '$LOCK';
  echo \"\$(date -u +%FT%TZ) poller start pid=\$\$ (detached)\" >> '$LOG';
  exec python3 -m backend.telegram_poll_continuous >> '$LOG' 2>&1
" < /dev/null > /dev/null 2>&1 &
disown 2>/dev/null || true
echo "launched detached poller"

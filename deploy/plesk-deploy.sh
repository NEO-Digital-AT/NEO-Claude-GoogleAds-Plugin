#!/usr/bin/env bash
# Builds and starts the container after a Plesk git deployment.
#
# WHY THIS IS A FILE AND NOT LINES IN THE PLESK TEXT BOX. Plesk runs each
# line of "additional deployment actions" in its OWN shell. A variable set
# on line one does not exist on line two, `cd` does not carry over, and
# `set -e` protects only the line it stands on. Everything therefore lives
# in one script, and the text box holds a single line that calls it.
#
# Plesk gives the deployment agent a sparse PATH, so every binary is named
# with its full path. The subscription user needs real shell access — with
# a chrooted shell it cannot reach docker at all.
#
#   Plesk -> Git -> Additional deployment actions, one line:
#       /bin/bash /var/www/vhosts/<domain>/<dir>/deploy/plesk-deploy.sh
#
# Exit code 0 when the server answers, non-zero otherwise — Plesk shows a
# failed deployment rather than a green one in front of a dead container.
set -euo pipefail

# The script's own directory, so the path appears in exactly one place:
# the line in the Plesk box. Symlinks are resolved first — called through
# one, the unresolved path would point at the link's directory and every
# file check below would look in the wrong place.
_self="${BASH_SOURCE[0]}"
while [ -L "$_self" ]; do
    _dir="$(cd -- "$(dirname -- "$_self")" && pwd)"
    _self="$(readlink "$_self")"
    case "$_self" in /*) ;; *) _self="$_dir/$_self" ;; esac
done
DEPLOY_DIR="$(cd -- "$(dirname -- "$_self")" && pwd)"

# On a Plesk server, Plesk's own nginx already holds ports 80 and 443 and
# already manages the domain's certificate. The Plesk variant therefore
# leaves the web server out and binds to the loopback address instead. It
# wins wherever it exists, so nobody has to remember a flag.
if [ -f "$DEPLOY_DIR/docker-compose.plesk.yml" ]; then
    COMPOSE_NAME="docker-compose.plesk.yml"
else
    COMPOSE_NAME="docker-compose.yml"
fi
COMPOSE_FILE="$DEPLOY_DIR/$COMPOSE_NAME"
DATA_DIR="$DEPLOY_DIR/data"
CONTAINER_UID=10001            # matches the user in the Dockerfile
HEALTH_TRIES=30                # times two seconds
SUDO=""

DOCKER=""
for candidate in /usr/bin/docker /usr/local/bin/docker; do
    [ -x "$candidate" ] && { DOCKER="$candidate"; break; }
done

step()  { printf '\n=== %s\n' "$1"; }
fail()  { printf 'FEHLER: %s\n' "$1" >&2; exit 1; }

step "Voraussetzungen"
[ -n "$DOCKER" ] || fail "docker nicht gefunden. Erwartet unter /usr/bin/docker."
[ -f "$COMPOSE_FILE" ] || fail "$COMPOSE_FILE fehlt."
if [ "$COMPOSE_NAME" = "docker-compose.yml" ]; then
    [ -f "$DEPLOY_DIR/Caddyfile" ] || fail "$DEPLOY_DIR/Caddyfile fehlt."
fi
echo "Aufbau: $COMPOSE_NAME"
[ -f "$DEPLOY_DIR/.env" ] || fail ".env fehlt. Einmalig anlegen:
  cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env
  nano $DEPLOY_DIR/.env      # Block aus: google-ads-auth.py --env
  chmod 600 $DEPLOY_DIR/.env
Sie steht bewusst nicht im Repository: sie enthaelt Refresh Token,
Client-Geheimnis und Developer Token."

# The subscription user is usually not allowed to talk to the docker
# socket. A sudo rule for exactly these commands is the safer answer than
# membership in the docker group, which is root by another name.
if ! "$DOCKER" info >/dev/null 2>&1; then
    if /usr/bin/sudo -n "$DOCKER" info >/dev/null 2>&1; then
        SUDO="/usr/bin/sudo -n"
        echo "docker ueber sudo erreichbar"
    else
        fail "Kein Zugriff auf docker, auch nicht ueber sudo.
Als root eine Regel anlegen (Benutzer und Pfad anpassen):
  echo '$(/usr/bin/id -un) ALL=(root) NOPASSWD: $DOCKER compose -f $COMPOSE_FILE *' \\
    > /etc/sudoers.d/neo-google-ads
  echo '$(/usr/bin/id -un) ALL=(root) NOPASSWD: /bin/chown $CONTAINER_UID\\:$CONTAINER_UID $DATA_DIR' \\
    >> /etc/sudoers.d/neo-google-ads
  chmod 440 /etc/sudoers.d/neo-google-ads && visudo -c"
    fi
else
    echo "docker direkt erreichbar"
fi

compose() { $SUDO "$DOCKER" compose -f "$COMPOSE_FILE" "$@"; }

step "Datenverzeichnis"
# Credentials, token and change log live here and survive a rebuild. The
# container runs as an unprivileged user and must be able to write to it.
/bin/mkdir -p "$DATA_DIR"
owner="$(/usr/bin/stat -c '%u' "$DATA_DIR")"
if [ "$owner" != "$CONTAINER_UID" ]; then
    if $SUDO /bin/chown "$CONTAINER_UID:$CONTAINER_UID" "$DATA_DIR" 2>/dev/null; then
        echo "Eigentuemer auf $CONTAINER_UID gesetzt"
    else
        echo "WARNUNG: $DATA_DIR gehoert $owner, nicht $CONTAINER_UID."
        echo "         Der Container kann darin moeglicherweise nicht schreiben."
        echo "         Als root:  chown $CONTAINER_UID:$CONTAINER_UID $DATA_DIR"
    fi
fi

step "Bauen und starten"
compose up -d --build --remove-orphans

step "Warten, bis der Server antwortet"
healthy=0
for _ in $(seq 1 "$HEALTH_TRIES"); do
    if compose ps --format '{{.Service}} {{.Status}}' 2>/dev/null \
        | /bin/grep -q 'google-ads-mcp.*healthy'; then
        healthy=1
        break
    fi
    /bin/sleep 2
done

compose ps --format 'table {{.Service}}\t{{.Status}}' || true

if [ "$healthy" -ne 1 ]; then
    echo
    echo "Letzte Protokollzeilen:"
    compose logs --tail=40 google-ads-mcp || true
    fail "Der Container wurde in $((HEALTH_TRIES * 2)) Sekunden nicht gesund."
fi

step "Server selbst fragen"
# 'healthy' says docker's check passed; this asks the process directly, so
# a green deployment really means a server that answers.
compose exec -T google-ads-mcp python3 -c \
    "import urllib.request;print('health:', urllib.request.urlopen('http://127.0.0.1:8788/health', timeout=5).status)" \
    || { compose logs --tail=40 google-ads-mcp || true; fail "Der Server antwortet nicht."; }

step "Bereitstellung fertig"

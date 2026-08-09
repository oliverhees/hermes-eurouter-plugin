#!/usr/bin/env bash
# Installiert das EU-Router-Plugin in eine lokale Hermes-Installation.
#
#   ./install.sh              Plugin installieren/aktualisieren
#   ./install.sh --with-shim  zusätzlich den Self-Heal-/Healthcheck-Shim
#                             unter ~/.local/bin/hermes installieren
#
# Idempotent: mehrfaches Ausführen ist sicher. Update-Flow:
#   git pull && ./install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
PLUGINS_LIVE="$HERMES_HOME_DIR/plugins/model-providers"

if [ ! -d "$HERMES_HOME_DIR" ]; then
  echo "FEHLER: $HERMES_HOME_DIR existiert nicht. Ist Hermes installiert?" >&2
  exit 1
fi

echo "Installiere EU-Router-Plugin nach $PLUGINS_LIVE/eurouter ..."
mkdir -p "$PLUGINS_LIVE/eurouter"
cp "$REPO_DIR/model-providers/eurouter/__init__.py" "$PLUGINS_LIVE/eurouter/__init__.py"
cp "$REPO_DIR/model-providers/eurouter/plugin.yaml" "$PLUGINS_LIVE/eurouter/plugin.yaml"
rm -rf "$PLUGINS_LIVE/eurouter/__pycache__"

# Modell-Listen-Cache leeren (1h-TTL-Disk-Cache, sonst wirkt ein Update
# des Plugins bis zu einer Stunde lang "wie nicht passiert").
CACHE_FILE="$HERMES_HOME_DIR/provider_models_cache.json"
if [ -f "$CACHE_FILE" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$CACHE_FILE" <<'PYEOF'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception:
    sys.exit(0)
if data.pop("eurouter", None) is not None:
    json.dump(data, open(path, "w"), indent=2)
    print("Modell-Listen-Cache für eurouter geleert.")
PYEOF
fi

if [ "${1:-}" = "--with-shim" ]; then
  SHIM_TARGET="$HOME/.local/bin/hermes"
  REAL_BIN="$HERMES_HOME_DIR/hermes-agent/venv/bin/hermes"
  if [ ! -x "$REAL_BIN" ]; then
    echo "WARNUNG: $REAL_BIN nicht gefunden, Shim wird trotzdem installiert" >&2
  fi
  mkdir -p "$HOME/.local/bin"
  if [ -f "$SHIM_TARGET" ] && ! grep -q "hermes-eurouter-plugin shim" "$SHIM_TARGET" 2>/dev/null; then
    cp "$SHIM_TARGET" "$SHIM_TARGET.bak.$(date +%Y%m%d%H%M%S)"
    echo "Bestehendes $SHIM_TARGET gesichert (.bak)."
  fi
  sed "s|@@REPO_DIR@@|$REPO_DIR|g" "$REPO_DIR/shim/hermes.template" > "$SHIM_TARGET"
  chmod +x "$SHIM_TARGET"
  echo "Shim installiert: $SHIM_TARGET (Quelle: $REPO_DIR)"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "HINWEIS: ~/.local/bin ist nicht im PATH — Shim wird so nicht gefunden." >&2 ;;
  esac
fi

echo ""
echo "Fertig. Nächste Schritte:"
echo "  1. EUROUTER_API_KEY in $HERMES_HOME_DIR/.env eintragen (falls noch nicht)"
echo "  2. Hermes komplett neu starten"
echo "  3. Im Modell-Picker den Provider 'EU Router' wählen — deine Routen erscheinen dort"

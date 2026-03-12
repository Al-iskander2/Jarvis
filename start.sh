#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  start.sh — Optimized OpenClaw Voice Bridge
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────────────────
C_BOLD='\033[1m'
C_CYAN='\033[1;36m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'
C_RED='\033[1;31m'
C_DIM='\033[2m'
C_RESET='\033[0m'

log()    { echo -e "${C_CYAN}[JARVIS]${C_RESET} $*"; }
ok()     { echo -e "${C_GREEN}  ✓${C_RESET} $*"; }
warn()   { echo -e "${C_YELLOW}  ⚠${C_RESET} $*"; }
error()  { echo -e "${C_RED}  ✗ ERROR:${C_RESET} $*" >&2; }

# ── Header ─────────────────────────────────────────────────────────────────────
clear
echo -e "${C_CYAN}${C_BOLD}"
echo -e "      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗"
echo -e "      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝"
echo -e "      ██║███████║██████╔╝██║   ██║██║███████╗"
echo -e " ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║"
echo -e " ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║"
echo -e "  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"
echo -e "${C_RESET}        Puente de Voz Optimizado v2.0 · OpenClaw Bridge"
echo -e ""

# ── Prep ───────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# 1. Finding suitable Python (3.9+)
if [ ! -d "$VENV_DIR" ]; then
    log "Buscando Python compatible (3.9+)..."
    PYTHON_CMD=""
    for cmd in python3.11 python3.10 python3.9 python3; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]; then
                PYTHON_CMD="$cmd"
                ok "Python $ver encontrado."
                break
            fi
        fi
    done

    if [ -z "$PYTHON_CMD" ]; then
        error "No se encontró Python 3.9+. Instálalo con 'brew install python@3.11'."
        exit 1
    fi

    log "Creando entorno virtual con $PYTHON_CMD..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
    ok "Entorno configurado."
fi

source "$VENV_DIR/bin/activate"

# 2. OpenClaw Preflight
log "Verificando OpenClaw Gateway..."
# Ensure we use the venv python for the cli
if ! python -m openclaw.cli status >/dev/null 2>&1; then
    warn "OpenClaw Gateway no responde."
    warn "Asegúrate de ejecutar 'openclaw gateway start'."
fi
ok "Checks de Bridge completados."

# 3. Port Cleanup
PORT=8000
if lsof -ti ":$PORT" &>/dev/null; then
    log "Liberando puerto $PORT..."
    kill -9 $(lsof -ti ":$PORT") 2>/dev/null || true
    sleep 1
fi

# ── Launch ─────────────────────────────────────────────────────────────────────
log "Arrancando JARVIS..."
echo -e ""
echo -e "  ✅ Bridge en: ${C_GREEN}http://localhost:$PORT${C_RESET}"
echo -e "  📖 API docs:  ${C_DIM}http://localhost:$PORT/docs${C_RESET}"
echo -e ""

# Reload support
RELOAD_FLAG=""
if [[ "${1:-}" == "--reload" ]]; then
    RELOAD_FLAG="--reload"
    log "Modo desarrollo (auto-reload) activado."
fi

(sleep 3 && open "http://localhost:$PORT" 2>/dev/null) &

export PYTHONPATH="$SCRIPT_DIR"
exec "$VENV_DIR/bin/uvicorn" main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    $RELOAD_FLAG \
    --log-level info

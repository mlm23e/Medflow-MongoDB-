#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/../backend" && pwd)"
RESET=false
CONFIRM_RESET=true

usage() {
    echo "Usage: bin/seed.sh [--reset] [--yes]" >&2
}

while (($#)); do
    case "$1" in
        --reset) RESET=true ;;
        --yes) CONFIRM_RESET=false ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Error: unknown option '$1'." >&2; usage; exit 2 ;;
    esac
    shift
done

if [ "$CONFIRM_RESET" = false ] && [ "$RESET" = false ]; then
    echo "Error: --yes can only be used with --reset." >&2
    usage
    exit 2
fi

if [ "$RESET" = true ] && [ "$CONFIRM_RESET" = true ]; then
    echo "Warning: --reset deletes the demo hospitals and their equipment, work orders, and reports."
    if ! read -r -p "Continue? Type 'yes' to confirm: " answer || [ "$answer" != "yes" ]; then
        echo "Reset cancelled." >&2
        exit 1
    fi
fi

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
    PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
else
    echo "Error: Python was not found. Run bin/setup.sh first or install Python 3." >&2
    exit 1
fi

cd "$BACKEND_DIR"
ARGS=()
if [ "$RESET" = true ]; then
    ARGS+=(--reset)
fi
"$PYTHON" -m app.scripts.seed_demo_data "${ARGS[@]}"
echo "MongoDB demo data is ready."
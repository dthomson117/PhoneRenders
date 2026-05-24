#!/usr/bin/env bash
# Cross-platform launcher for render_screens.py.
# Works on macOS, Linux, and Windows under Git Bash / WSL.
#
# Usage:
#   ./render.sh              # render both iOS + Android (default)
#   ./render.sh ios          # iOS only
#   ./render.sh android      # Android only
#   ./render.sh both | all   # explicit "render everything"
#
# Override Blender location with: BLENDER_EXE=/path/to/blender ./render.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLEND_FILE="$SCRIPT_DIR/phones.blend"
SCRIPT_FILE="$SCRIPT_DIR/render_screens.py"

# --- platform filter (positional arg 1) ----------------------------------
# Read by render_screens.py via the RENDER_PLATFORMS env var.
PLATFORM_ARG="${1:-}"
PLATFORM_LC="$(printf '%s' "$PLATFORM_ARG" | tr '[:upper:]' '[:lower:]')"
case "$PLATFORM_LC" in
  "")
    PLATFORM_LABEL="iOS, Android (all)"
    ;;
  ios)
    export RENDER_PLATFORMS="iOS"
    PLATFORM_LABEL="iOS"
    ;;
  android)
    export RENDER_PLATFORMS="Android"
    PLATFORM_LABEL="Android"
    ;;
  both|all)
    PLATFORM_LABEL="iOS, Android (all)"
    ;;
  *)
    echo "ERROR: Unknown platform '$PLATFORM_ARG'. Use: ios, android, both, or no argument." >&2
    exit 1
    ;;
esac

# --- find Blender --------------------------------------------------------
find_blender() {
  # 1. Manual override.
  if [[ -n "${BLENDER_EXE:-}" && -x "${BLENDER_EXE:-}" ]]; then
    return 0
  fi

  # 2. PATH.
  if command -v blender >/dev/null 2>&1; then
    BLENDER_EXE="$(command -v blender)"
    return 0
  fi

  # 3. Common install locations on macOS / Linux.
  local candidates=(
    "/Applications/Blender.app/Contents/MacOS/Blender"
    "$HOME/Applications/Blender.app/Contents/MacOS/Blender"
    "/usr/local/bin/blender"
    "/opt/blender/blender"
    "/snap/bin/blender"
    "/var/lib/flatpak/exports/bin/org.blender.Blender"
    "$HOME/.local/bin/blender"
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      BLENDER_EXE="$c"
      return 0
    fi
  done

  # 4. Windows install locations (Git Bash / WSL / MSYS).
  #    ProgramFiles(x86) has parens in its name so it's read via printenv.
  local pf="${ProgramFiles:-}"
  local pfx86
  pfx86="$(printenv 'ProgramFiles(x86)' 2>/dev/null || true)"
  local localapp="${LOCALAPPDATA:-}"
  local base dir
  for base in \
    "${pf:+$pf/Blender Foundation}" \
    "${pfx86:+$pfx86/Blender Foundation}" \
    "${localapp:+$localapp/Programs/Blender Foundation}" \
    "/c/Program Files/Blender Foundation" \
    "/c/Program Files (x86)/Blender Foundation" \
    "/mnt/c/Program Files/Blender Foundation" \
    "/mnt/c/Program Files (x86)/Blender Foundation"
  do
    [[ -z "$base" || ! -d "$base" ]] && continue
    # Pick the newest Blender* subfolder (lexicographic; fine for 4.x/5.x).
    while IFS= read -r dir; do
      if [[ -x "$dir/blender.exe" ]]; then
        BLENDER_EXE="$dir/blender.exe"
        return 0
      fi
    done < <(find "$base" -maxdepth 1 -type d -name 'Blender*' 2>/dev/null | sort -r)
  done

  return 1
}

if ! find_blender; then
  cat >&2 <<'EOF'

ERROR: Could not find Blender automatically.

Tried:
  - BLENDER_EXE environment variable
  - PATH (command -v blender)
  - /Applications/Blender.app                          (macOS)
  - /usr/local/bin, /opt, /snap, flatpak, ~/.local/bin (Linux)
  - Program Files\Blender Foundation\Blender X.Y       (Windows via Git Bash / WSL)

Fix by one of:
  1. BLENDER_EXE=/path/to/blender ./render.sh
  2. Put 'blender' on your PATH.
  3. Edit this script and hardcode BLENDER_EXE near the top.

EOF
  exit 1
fi

echo "Blender:    $BLENDER_EXE"
echo "Blend file: $BLEND_FILE"
echo "Script:     $SCRIPT_FILE"
echo "Platforms:  $PLATFORM_LABEL"
echo

if [[ ! -f "$BLEND_FILE" ]]; then
  echo "ERROR: .blend file not found at $BLEND_FILE" >&2
  exit 1
fi
if [[ ! -f "$SCRIPT_FILE" ]]; then
  echo "ERROR: Python script not found at $SCRIPT_FILE" >&2
  exit 1
fi

set +e
"$BLENDER_EXE" --background "$BLEND_FILE" --python "$SCRIPT_FILE"
EXITCODE=$?
set -e

echo
if [[ $EXITCODE -ne 0 ]]; then
  echo "=== Render failed with exit code $EXITCODE ==="
else
  echo "=== Done ==="
fi

read -r -p "Press Enter to close..." _
exit $EXITCODE

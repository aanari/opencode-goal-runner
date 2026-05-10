#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="opencode-goal-runner"
PREFIX="${PREFIX:-$HOME/.local}"
BINDIR="${BINDIR:-$PREFIX/bin}"
DEST="$BINDIR/$BIN_NAME"
RELEASE_BIN="$ROOT/target/release/$BIN_NAME"

usage() {
  cat <<USAGE
Usage: ./install.sh [--check | --uninstall | --symlink | --help]

Default: build release binary and copy it to ~/.local/bin/opencode-goal-runner.

Options:
  --check      Run cargo test, cargo llvm-cov --fail-under-lines 95, and cargo build --release.
  --uninstall  Remove only the installed opencode-goal-runner binary or symlink.
  --symlink    Build release binary and symlink it into ~/.local/bin for dev mode.
  --help       Show this help.

Environment:
  PREFIX       Install prefix. Default: ~/.local.
  BINDIR       Install directory. Default: $PREFIX/bin.
USAGE
}

path_guidance() {
  case ":$PATH:" in
    *":$BINDIR:"*) echo "$BINDIR is already on PATH" ;;
    *) echo "add this to your shell profile: export PATH=\"$BINDIR:\$PATH\"" ;;
  esac
}

check_tools() {
  command -v cargo >/dev/null 2>&1 || {
    echo "error: cargo is required to build from source." >&2
    exit 1
  }
}

build_release() {
  check_tools
  (cd "$ROOT" && cargo build --release)
}

install_copy() {
  build_release
  mkdir -p "$BINDIR"
  install -m 0755 "$RELEASE_BIN" "$DEST"
  echo "installed $DEST"
  path_guidance
}

install_symlink() {
  build_release
  mkdir -p "$BINDIR"
  ln -sfn "$RELEASE_BIN" "$DEST"
  echo "symlinked $DEST -> $RELEASE_BIN"
  path_guidance
}

uninstall() {
  if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    rm "$DEST"
    echo "removed $DEST"
    return
  fi
  echo "nothing to remove at $DEST"
}

run_check() {
  check_tools
  (cd "$ROOT" && cargo test)
  (cd "$ROOT" && cargo llvm-cov --fail-under-lines 95)
  (cd "$ROOT" && cargo build --release)
}

case "${1:-}" in
  "") install_copy ;;
  --check) run_check ;;
  --uninstall) uninstall ;;
  --symlink) install_symlink ;;
  --help|-h) usage ;;
  *)
    echo "error: unknown option $1" >&2
    usage >&2
    exit 1
    ;;
esac

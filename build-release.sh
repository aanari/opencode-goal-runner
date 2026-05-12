#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="opencode-goal-runner"
DIST="$ROOT/dist"
MAC_TARGET="aarch64-apple-darwin"
LINUX_TARGET="x86_64-unknown-linux-musl"
BUILD_LINUX=1
RUN_CHECKS=0

usage() {
  cat <<USAGE
Usage: ./build-release.sh [--check] [--mac-only] [--help]

Build release binaries into ./dist.

Artifacts:
  dist/$BIN_NAME-$MAC_TARGET
  dist/$BIN_NAME-$LINUX_TARGET

Options:
  --check     Run cargo test before building.
  --mac-only  Build only the macOS Apple Silicon binary.
  --help      Show this help.

Linux cross-build requirements:
  brew install zig
  cargo install cargo-zigbuild
  rustup target add $LINUX_TARGET
USAGE
}

check_cargo() {
  command -v cargo >/dev/null 2>&1 || {
    echo "error: cargo is required." >&2
    exit 1
  }
  command -v rustup >/dev/null 2>&1 || {
    echo "error: rustup is required to verify installed build targets." >&2
    exit 1
  }
}

check_target() {
  local target="$1"
  rustup target list --installed | grep -qx "$target" || {
    echo "error: Rust target $target is not installed." >&2
    echo "install with: rustup target add $target" >&2
    exit 1
  }
}

check_zigbuild() {
  command -v cargo-zigbuild >/dev/null 2>&1 || {
    echo "error: cargo-zigbuild is required for Linux cross-builds." >&2
    echo "install with: cargo install cargo-zigbuild" >&2
    exit 1
  }
  command -v zig >/dev/null 2>&1 || {
    echo "error: zig is required for Linux cross-builds." >&2
    echo "install with: brew install zig" >&2
    exit 1
  }
}

copy_artifact() {
  local target="$1"
  local source="$ROOT/target/$target/release/$BIN_NAME"
  local dest="$DIST/$BIN_NAME-$target"
  install -m 0755 "$source" "$dest"
  echo "built $dest"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check) RUN_CHECKS=1 ;;
    --mac-only) BUILD_LINUX=0 ;;
    --help|-h) usage; exit 0 ;;
    *)
      echo "error: unknown option $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

check_cargo
check_target "$MAC_TARGET"
if [ "$BUILD_LINUX" -eq 1 ]; then
  check_target "$LINUX_TARGET"
  check_zigbuild
fi

mkdir -p "$DIST"

if [ "$RUN_CHECKS" -eq 1 ]; then
  (cd "$ROOT" && cargo test --locked)
fi

(cd "$ROOT" && cargo build --release --locked --target "$MAC_TARGET")
copy_artifact "$MAC_TARGET"

if [ "$BUILD_LINUX" -eq 1 ]; then
  (cd "$ROOT" && cargo zigbuild --release --locked --target "$LINUX_TARGET")
  copy_artifact "$LINUX_TARGET"
fi

ls -lh "$DIST"/$BIN_NAME-*

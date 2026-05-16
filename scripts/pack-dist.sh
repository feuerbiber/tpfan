#!/usr/bin/env bash
# Erzeugt dist/tpfan-<VERSION>.tar.gz mit allen Dateien, die das
# Install-Skript zum Aufsetzen des Tools braucht. Reproduzierbar:
# fixe mtime, fixe Owner/Group — damit derselbe Source-Stand auch
# byte-identische Archive produziert.
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0"/..)"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' daemon/src/tpfan_daemon/__init__.py)"
if [[ -z "$VERSION" ]]; then
    echo "pack-dist: konnte VERSION nicht ermitteln" >&2
    exit 1
fi

mkdir -p dist
# alte Tarballs entfernen, damit nur das aktuelle Release im dist/ liegt.
rm -f dist/tpfan-*.tar.gz

OUT="dist/tpfan-${VERSION}.tar.gz"

tar \
    --owner=0 --group=0 --numeric-owner \
    --sort=name --mtime='2020-01-01 00:00:00 UTC' \
    --transform "s,^,tpfan-${VERSION}/," \
    --exclude='__pycache__' \
    --exclude='*.egg-info' \
    --exclude='.coverage' \
    --exclude='build' \
    --exclude='dist' \
    --exclude='scripts/pack-dist.sh' \
    -czf "$OUT" \
    daemon/pyproject.toml daemon/src \
    gui/pyproject.toml gui/src \
    packaging scripts README.md LICENSE

echo "pack-dist: $OUT ($(stat -c %s "$OUT") Bytes)"

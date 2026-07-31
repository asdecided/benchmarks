#!/usr/bin/env bash
set -euo pipefail

version="${1:-0.26.0}"
version="${version#v}"

archive="asdecided-x86_64-unknown-linux-gnu.tar.gz"
case "$version" in
  0.23.1)
    digest="51cce8025a7cb2f8b2caea93a8ea71be0ad8c5c316fd0ecced688267bf97b8ac"
    ;;
  0.26.0)
    digest="4d7f2fa85686af8d1006aa530928f60e2cd3d13d8560b303495f2784d1b8bbed"
    ;;
  *)
    echo "::error::No verified checksum is recorded for asdecided-core $version"
    exit 1
    ;;
esac
install_dir="${RUNNER_TEMP}/asdecided-${version}"
download="${RUNNER_TEMP}/${archive}"
url="https://github.com/asdecided/core/releases/download/v${version}/${archive}"

mkdir -p "$install_dir"
curl --fail --location --retry 3 --silent --show-error "$url" --output "$download"
echo "$digest  $download" | sha256sum --check -
tar -xzf "$download" -C "$install_dir"

echo "$install_dir" >> "$GITHUB_PATH"
"$install_dir/decided" --version

#!/usr/bin/env bash
set -euo pipefail

version="${1:-0.23.1}"
version="${version#v}"
if [[ "$version" != "0.23.1" ]]; then
  echo "::error::No verified checksum is recorded for asdecided-core $version"
  exit 1
fi

archive="asdecided-x86_64-unknown-linux-gnu.tar.gz"
digest="51cce8025a7cb2f8b2caea93a8ea71be0ad8c5c316fd0ecced688267bf97b8ac"
install_dir="${RUNNER_TEMP}/asdecided-${version}"
download="${RUNNER_TEMP}/${archive}"
url="https://github.com/asdecided/core/releases/download/v${version}/${archive}"

mkdir -p "$install_dir"
curl --fail --location --retry 3 --silent --show-error "$url" --output "$download"
echo "$digest  $download" | sha256sum --check -
tar -xzf "$download" -C "$install_dir"

echo "$install_dir" >> "$GITHUB_PATH"
"$install_dir/decided" --version

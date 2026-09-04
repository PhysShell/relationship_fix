#!/bin/sh
# Builds the protocol core as a WASI command.
#
# Requires the official GHC WebAssembly backend, which is a separate cross
# compiler rather than the GHC that builds the application:
#
#   curl https://gitlab.haskell.org/haskell-wasm/ghc-wasm-meta/-/raw/master/bootstrap.sh | sh
#   . ~/.ghc-wasm/env
#
# Domain.hs takes GHC2021 and DerivingStrategies from the package's
# default-extensions, so this direct compiler invocation has to pass them.
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
out=${1:-$root/experiments/wasm-core/relationship-fix-core.wasm}
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

wasm32-wasi-ghc \
  -XGHC2021 -XDerivingStrategies \
  -Wall -Werror \
  -i"$root/src/annotation-web/src" \
  -outputdir "$workdir" \
  -o "$out" \
  "$root/experiments/wasm-core/Main.hs"

echo "built $out"

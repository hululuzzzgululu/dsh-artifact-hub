#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hub_dir="$(cd "${script_dir}/.." && pwd)"

cd "${hub_dir}"
exec uv run python -m api.main

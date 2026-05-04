#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  printf 'usage: %s <label> <command> [args...]\n' "$0" >&2
  exit 2
fi

label="$1"
shift
command=("$@")

interval="${MELIX_CI_PROGRESS_INTERVAL_SECONDS:-60}"
if ! [[ "$interval" =~ ^[1-9][0-9]*$ ]]; then
  printf 'MELIX_CI_PROGRESS_INTERVAL_SECONDS must be a positive integer\n' >&2
  exit 2
fi

started_at="$(date +%s)"
printf '[melix-ci] %s started:' "$label" >&2
for arg in "${command[@]}"; do
  printf ' %q' "$arg" >&2
done
printf '\n' >&2

heartbeat() {
  while true; do
    sleep "$interval"
    now="$(date +%s)"
    elapsed=$((now - started_at))
    printf '[melix-ci] %s still running after %ss\n' "$label" "$elapsed" >&2
  done
}

heartbeat &
heartbeat_pid="$!"
cleanup() {
  kill "$heartbeat_pid" 2>/dev/null || true
  wait "$heartbeat_pid" 2>/dev/null || true
}
trap cleanup EXIT

set +e
"${command[@]}"
status="$?"
set -e

finished_at="$(date +%s)"
elapsed=$((finished_at - started_at))
printf '[melix-ci] %s completed rc=%s elapsed=%ss\n' "$label" "$status" "$elapsed" >&2
exit "$status"

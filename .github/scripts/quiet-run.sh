#!/usr/bin/env bash
# quiet-run.sh LABEL STDOUT_FILE -- command [args...]
#
# This repo is public, and so are its Actions logs. Any script that reads the
# private portfolio data (holdings, stops, closed positions, recommendations)
# must run through this wrapper: stdout goes to STDOUT_FILE (usually a report
# inside data/, which is committed to the private repo and emailed), stderr
# goes to a file in $CI_LOG_DIR. Nothing the command prints reaches the log.
#
# On failure the log gets only the exit code and the exception class name —
# never the message, since e.g. yfinance errors quote the ticker.
#
# STDOUT_FILE "-" means "not needed": stdout lands next to stderr in $CI_LOG_DIR.
set -uo pipefail

if [ $# -lt 4 ] || [ "$3" != "--" ]; then
  echo "usage: quiet-run.sh LABEL STDOUT_FILE -- command [args...]" >&2
  exit 2
fi
label=$1; out=$2; shift 3

logdir=${CI_LOG_DIR:-data/ci-logs}
mkdir -p "$logdir"
prefix="$logdir/${GITHUB_WORKFLOW:-local}-${GITHUB_RUN_ID:-0}-$label"
err="$prefix.stderr.txt"
[ "$out" = "-" ] && out="$prefix.stdout.txt"

"$@" > "$out" 2> "$err"
rc=$?

if [ $rc -ne 0 ]; then
  etype=$(grep -oE '^[A-Za-z_.]*(Error|Exception|Interrupt|Exit)\b' "$err" | tail -n1 || true)
  echo "::error::$label failed (exit $rc${etype:+, $etype}) — output kept out of the public log, see $err"
else
  echo "$label: ok"
fi

# keep only the newest 30 log files, so data/ci-logs doesn't grow forever
# shellcheck disable=SC2012  # ls -t on our own run-id filenames: sort by mtime is the point
(cd "$logdir" && ls -1t -- *.txt 2>/dev/null | tail -n +31 | xargs -r rm --)
exit $rc

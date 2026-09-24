#!/usr/bin/env bash
# require-env.sh NAME [NAME...]
#
# Fail fast when a secret the workflow needs is empty. A missing repo secret
# expands to "" silently; without this check the job dies several steps later
# with an unrelated-looking error (e.g. "client-id must be set", "cd: data: No
# such file or directory") and the real cause is buried under the cascade.
missing=()
for name in "$@"; do
  [ -n "${!name:-}" ] || missing+=("$name")
done
if [ ${#missing[@]} -gt 0 ]; then
  for name in "${missing[@]}"; do
    echo "::error::Missing repository secret $name — Settings → Secrets and variables → Actions (see GITHUB_APP_SETUP.md)"
  done
  exit 1
fi
echo "all ${#} required secrets present"

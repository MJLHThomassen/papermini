#!/usr/bin/env bash
# Install Ubuntu packages in CI, coping with a slow or unreachable package mirror:
#
#   bash .github/apt-install.sh libegl1 libgl1 ...
#
# Each download gives up after 15 seconds instead of hanging, and the whole
# update + install is tried three times, 15 seconds apart. When the mirror does not
# answer, the step fails with a clear error instead of running into the job's time
# limit.
set -u

apt=(sudo apt-get -q
     -o Acquire::Retries=2
     -o Acquire::http::Timeout=15
     -o Acquire::https::Timeout=15)

for try in 1 2 3; do
  if "${apt[@]}" update && "${apt[@]}" install -y --no-install-recommends "$@"; then
    exit 0
  fi
  if [[ $try -lt 3 ]]; then
    echo "::warning::Installing $* failed (try $try of 3); trying again in 15 seconds"
    sleep 15
  fi
done
echo "::error::Could not install $*: the Ubuntu package mirror did not answer. Re-run the job later."
exit 1

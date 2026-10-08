#!/bin/sh
set -eu

# Used physical RAM excludes reclaimable file-backed and purgeable caches.
# File-backed pages already include speculative read-ahead pages.
total=$(/usr/sbin/sysctl -n hw.memsize)
stop() {
    for job in $(jobs -p); do kill "$job" 2>/dev/null || :; done
    wait
    exit 0
}
trap stop TERM HUP INT
while :; do
    /usr/bin/vm_stat | /usr/bin/awk -v total="$total" '
        NR == 1 { match($0, /[0-9]+/); page_size = substr($0, RSTART, RLENGTH) }
        /Pages free:/ { free_pages += $NF + 0 }
        /File-backed pages:|Pages purgeable:/ { cached_pages += $NF + 0 }
        END {
            if (total > 0 && page_size > 0) {
                printf "RAM %.0f%%\n", 100 * (total - (free_pages + cached_pages) * page_size) / total
            } else {
                print "RAM ?"
            }
        }
    '
    [ "${1-}" = --watch ] || break
    sleep 5 &
    wait
done

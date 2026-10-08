#!/bin/sh
set -eu

# Average process CPU share across logical cores. ps follows the locale's decimal separator.
cores=$(/usr/sbin/sysctl -n hw.logicalcpu)
stop() {
    for job in $(jobs -p); do kill "$job" 2>/dev/null || :; done
    wait
    exit 0
}
trap stop TERM HUP INT
while :; do
    LC_ALL=C /bin/ps -A -o %cpu= | /usr/bin/awk -v cores="$cores" '
        { total += $1 }
        END {
            if (cores > 0) {
                printf "CPU %.0f%%\n", total / cores
            } else {
                print "CPU ?"
            }
        }
    '
    [ "${1-}" = --watch ] || break
    sleep 5 &
    wait
done

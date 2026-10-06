#!/bin/sh
set -eu

# Average process CPU share across logical cores. ps follows the locale's decimal separator.
cores=$(/usr/sbin/sysctl -n hw.logicalcpu)
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

#!/bin/sh

set -e

cd scowl/

apply() {
    if [ -e "data/$1.new" ]; then
        echo $1
        awk 'BEGIN { print "" } NR==1 && /^#::/ {next} {print}' "data/$1.new" >> "data/$1"
        rm -f "data/$1.old"
        mv "data/$1.new" "data/$1.old"
    fi
}

apply fixes
apply extra
apply signature
./cleanup.sh



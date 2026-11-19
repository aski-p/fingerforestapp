#!/bin/sh
# apksigner via the PGX Android builder image. Usage: apksigner-docker.sh verify --print-certs <apk>
set -eu
last=""; for a in "$@"; do last="$a"; done
dir="$(cd "$(dirname "$last")" && pwd)"; base="$(basename "$last")"
n=$#; i=0; set -- "$@" ; args=""
for a in "$@"; do i=$((i+1)); [ "$i" -lt "$n" ] && args="$args '$a'"; done
eval "exec docker run --rm -v \"$dir:/a:ro\" \"${FF_ANDROID_IMAGE:-dropday-apk-builder:gradle-37}\" sh -c 'java -jar \"\$APKSIGNER_JAR\" $args /a/$base'"

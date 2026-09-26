#!/bin/sh
# The exit criterion, executable: `docker compose up` on a checkout serves the
# interface and indexes an upload.
#
# It brings the stack up, waits for the API to report ready, uploads one
# picture, waits for the *worker* to extract its vectors (the API's own runner
# is off in the stack), searches for it, and then opens the interface in a real
# browser to see that the picture actually rendered — a page of broken images
# answers 200 to `curl`, so the last step asks the browser instead.
#
# Then it takes the stack down and leaves the volumes alone: the media, the
# weights and the database survive, which is the other half of the promise.
#
#     sh scripts/stack_smoke.sh [picture]
#
# Ports come from the environment, because 8000 and 8501 are taken on some
# machines, and `FORWARD_DB_PORT` is overridden on purpose: if any service in
# the stack were reaching the database through the port the host publishes
# rather than through `db:5432`, this run would fail.
set -eu

: "${COMPOSE_PROJECT_NAME:=semanticshelf-stack}"
: "${APP_PORT:=8010}"
: "${UI_PORT:=8511}"
: "${FORWARD_DB_PORT:=5444}"
: "${BIND_ADDRESS:=127.0.0.1}"
export COMPOSE_PROJECT_NAME APP_PORT UI_PORT FORWARD_DB_PORT BIND_ADDRESS

API="http://${BIND_ADDRESS}:${APP_PORT}"
UI="http://${BIND_ADDRESS}:${UI_PORT}"
PICTURE="${1:-}"
#: How long to wait for the worker. A cold model cache means downloading a few
#: gigabytes from the Hub; a warm one means seconds.
INDEX_TIMEOUT_SECONDS="${INDEX_TIMEOUT_SECONDS:-900}"

say() { printf '\n== %s\n' "$1"; }

if ! docker compose version >/dev/null 2>&1; then
    echo "stack-smoke: this needs the docker compose plugin (v2)" >&2
    exit 1
fi

say "bringing the stack up (project $COMPOSE_PROJECT_NAME, api $APP_PORT, ui $UI_PORT, db $FORWARD_DB_PORT)"
make stack

say "the API says"
curl -fsS "$API/ready"
printf '\n'

if [ -z "$PICTURE" ]; then
    PICTURE=$(mktemp -t stack-smoke-XXXXXX.png)
    trap 'rm -f "$PICTURE"' EXIT
    uv run --quiet python -c "
import sys
from PIL import Image
Image.new('RGB', (320, 240), (40, 90, 160)).save(sys.argv[1])
" "$PICTURE"
fi

say "uploading $PICTURE"
upload=$(curl -fsS -X POST "$API/api/v1/assets" -F "file=@$PICTURE" -F "tags=stack-smoke")
asset=$(printf '%s' "$upload" | uv run --quiet python -c "import json,sys; print(json.load(sys.stdin)['id'])")
printf 'asset %s\n' "$asset"
printf '%s' "$upload" | uv run --quiet python -c "
import json, sys
status = json.load(sys.stdin)['index_status']
assert all(state == 'pending' for state in status.values()), status
print('queued, not extracted by the API:', json.dumps(status))
"

say "waiting for the worker (up to ${INDEX_TIMEOUT_SECONDS}s)"
waited=0
while :; do
    status=$(curl -fsS "$API/api/v1/assets/$asset" |
        uv run --quiet python -c "import json,sys; print(json.dumps(json.load(sys.stdin)['index_status']))")
    case "$status" in
        *pending* | *running*) : ;;
        *failed*)
            echo "stack-smoke: the worker gave up: $status" >&2
            exit 1
            ;;
        *)
            printf 'indexed after %ss: %s\n' "$waited" "$status"
            break
            ;;
    esac
    if [ "$waited" -ge "$INDEX_TIMEOUT_SECONDS" ]; then
        echo "stack-smoke: still $status after ${waited}s" >&2
        exit 1
    fi
    sleep 5
    waited=$((waited + 5))
done

say "searching for it"
curl -fsS "$API/api/v1/search/text?q=a+photo&limit=10" |
    ASSET="$asset" uv run --quiet python -c "
import json, os, sys
page = json.load(sys.stdin)
found = [item for item in page['items'] if item['asset']['id'] == os.environ['ASSET']]
if not found:
    print('stack-smoke: the search did not find the picture that was just indexed', file=sys.stderr)
    raise SystemExit(1)
print('found it, score', round(found[0]['score'], 3))
"

say "opening the interface in a browser"
uv run --quiet --group ui --group screenshots python scripts/stack_browser_check.py "$UI"

say "taking the stack down (volumes are kept)"
docker compose down

remaining=$(docker volume ls --quiet --filter "name=${COMPOSE_PROJECT_NAME}_" | wc -l)
printf 'volumes still there: %s\n' "$remaining"
[ "$remaining" -ge 3 ] || {
    echo "stack-smoke: the volumes were supposed to survive the stack" >&2
    exit 1
}

say "stack-smoke: the stack served the interface and indexed an upload"

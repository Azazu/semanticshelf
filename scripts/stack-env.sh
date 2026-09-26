#!/bin/sh
# Make a clean checkout configurable, once.
#
# The compose file demands the database's name, user and secret through
# `:?required`, and the file that answers them is not in git — only its template
# is. So a fresh clone cannot start the stack until this has run: it copies the
# template and replaces the one marker in it with a value generated here.
#
# Three rules it keeps:
#   * it never overwrites an existing file — a configuration somebody edited is
#     theirs, and this is not a reset command;
#   * the generated value is generated *here*, never carried in a committed
#     file: anything a repository ships is shared by every deployment that ever
#     clones it;
#   * it prints what it did, never what it wrote.
set -eu

TEMPLATE="${STACK_ENV_TEMPLATE:-.env.example}"
TARGET="${STACK_ENV_FILE:-.env}"
MARKER="${STACK_ENV_MARKER:-__GENERATED__}"

if [ -e "$TARGET" ]; then
    echo "stack-env: $TARGET is already there — leaving it alone"
    exit 0
fi

if [ ! -f "$TEMPLATE" ]; then
    echo "stack-env: no template at $TEMPLATE, so there is nothing to copy" >&2
    exit 1
fi

if ! grep -q "$MARKER" "$TEMPLATE"; then
    echo "stack-env: $TEMPLATE carries no $MARKER, so nothing would be generated." >&2
    echo "stack-env: the template's database line is meant to read ${MARKER} as its" >&2
    echo "stack-env: value, which is what this script replaces." >&2
    exit 1
fi

# 32 characters from the kernel's own source. `tr -dc` over /dev/urandom needs
# nothing a POSIX shell does not already have, which is the point: the promise
# of the stack is that the host needs Docker and no toolchain.
generated=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)
if [ ${#generated} -ne 32 ]; then
    echo "stack-env: could not generate a value" >&2
    exit 1
fi

value_of() {  # value_of <key> <file>
    awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$2"
}

umask 077
partial="$TARGET.partial"
awk -v marker="$MARKER" -v value="$generated" \
    '{ gsub(marker, value); print }' "$TEMPLATE" > "$partial"

# The database is opened twice over: by its parts, which the container is
# created from, and by a URL, which every host tool connects with. Two places
# that must agree is one place too many — a template where they drift creates a
# database with one set of values and connects to it with another, and the
# failure arrives as an authentication error or, worse, as a connection to some
# *other* database that happens to be on that port.
#
# So the URL is not copied from the template: it is composed here from what this
# file itself says, every time. The user, the name, the published port and the
# generated value are read back out of the file that was just written, which is
# also what makes a template with non-default values come out right (Gate 2 of
# change 15: the URL had the defaults baked in, and changing `DB_USER`,
# `DB_NAME` or `FORWARD_DB_PORT` left it pointing at the old ones).
user=$(value_of DB_USER "$partial")
name=$(value_of DB_NAME "$partial")
port=${FORWARD_DB_PORT:-$(value_of FORWARD_DB_PORT "$partial")}
port=${port:-5433}
host=${DB_HOST_IN_URL:-127.0.0.1}

if [ -z "$user" ] || [ -z "$name" ]; then
    rm -f "$partial"
    echo "stack-env: $TEMPLATE does not say which user and database to use," >&2
    echo "stack-env: so the URL every host tool connects with cannot be built." >&2
    exit 1
fi

composed="postgresql+asyncpg://${user}:${generated}@${host}:${port}/${name}"
awk -v line="DATABASE_URL=$composed" \
    'BEGIN { done = 0 }
     /^DATABASE_URL=/ { print line; done = 1; next }
     { print }
     END { if (!done) print line }' "$partial" > "$partial.url" && mv "$partial.url" "$partial"

mv "$partial" "$TARGET"
echo "stack-env: wrote $TARGET from $TEMPLATE — a generated value where the marker was,"
echo "stack-env: and a database URL composed from ${user}@${host}:${port}/${name}"

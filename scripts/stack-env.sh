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

# The marker usually appears more than once — the database is opened by a URL as
# well as by its parts — and a template that fills one and not the other creates
# a database with one secret and connects to it with another. That was found at
# Gate 2 of change 15, in a template where the URL carried a literal. Nothing
# half-written is left behind: the file only moves into place if this holds.
generated_value=$(value_of DB_PASSWORD "$partial")
url=$(value_of DATABASE_URL "$partial")
if [ -n "$generated_value" ] && [ -n "$url" ]; then
    case "$url" in
        *"$generated_value"*) ;;
        *)
            rm -f "$partial"
            echo "stack-env: $TEMPLATE fills the database's own line but not its URL." >&2
            echo "stack-env: put $MARKER where the URL's password is too, so one run" >&2
            echo "stack-env: fills both — otherwise the database is created with one" >&2
            echo "stack-env: value and every host tool connects with another." >&2
            exit 1
            ;;
    esac
fi

mv "$partial" "$TARGET"
echo "stack-env: wrote $TARGET from $TEMPLATE, with the marker replaced by a generated value"

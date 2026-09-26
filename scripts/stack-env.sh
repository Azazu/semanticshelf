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

umask 077
awk -v marker="$MARKER" -v value="$generated" \
    '{ gsub(marker, value); print }' "$TEMPLATE" > "$TARGET"

echo "stack-env: wrote $TARGET from $TEMPLATE, with the marker replaced by a generated value"

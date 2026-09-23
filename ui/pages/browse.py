"""Browse: what the store holds, and everything it knows about one picture.

Like every Streamlit page this file runs top to bottom on each interaction, so
anything that changes what should be *shown* — a page turn, a filter, a
deletion — changes state and reruns rather than drawing and then changing.

Resetting a widget deserves its own note: a widget's value cannot be rewritten
after it has been created in the same run, so the ones that must be cleared
carry a generation in their key. Bumping the generation makes the next run
build a fresh widget with its default.
"""

import streamlit as st

from ui.client import ServiceError, address_of
from ui.shell import refused, service, thumbnails

PAGE_SIZE = 12

for key, value in {"offset": 0, "tag": None, "generation": 0}.items():
    st.session_state.setdefault(f"browse_{key}", value)

st.title("Browse")
st.caption("Everything stored, newest first. Pick a tag to narrow it, or a picture to open it.")

client = service()
generation = st.session_state.browse_generation

try:
    census = client.tags()["items"]
except ServiceError as error:
    refused(error)
    census = []

labels = {f"{entry['tag']} ({entry['assets']})": entry["tag"] for entry in census}
# The tag selector keeps its own value: the generation below resets the widgets
# that must be *cleared* when the corpus under them changes, and this is the one
# that changes it.
choice = st.selectbox("Tag", options=["(any)", *labels], index=0, key="browse_choice")
tag = labels.get(choice)

if tag != st.session_state.browse_tag:
    # A different corpus is being looked at: page one of it, nothing opened.
    st.session_state.browse_tag = tag
    st.session_state.browse_offset = 0
    st.session_state.browse_generation += 1
    st.rerun()

try:
    page = client.assets(limit=PAGE_SIZE, offset=st.session_state.browse_offset, tags_all=tag)
except ServiceError as error:
    refused(error)
    page = {"items": [], "has_more": False}

items = page["items"]
first_page = st.session_state.browse_offset == 0

if not items and first_page:
    st.info(
        f"Nothing carries **{tag}**."
        if tag
        else "Nothing here yet. `make demo` fills the store with a corpus to look at."
    )
elif not items:
    st.info("Nothing on this page — the store got smaller while you were looking.")
else:
    shown = f"Showing {len(items)} from {st.session_state.browse_offset + 1}."
    st.write(f"{shown} Narrowed by **{tag}**." if tag else shown)
    thumbnails(items)

back, forward = st.columns(2)
if not first_page and back.button("Previous page"):
    st.session_state.browse_offset = max(0, st.session_state.browse_offset - PAGE_SIZE)
    st.session_state.browse_generation += 1
    st.rerun()
if page["has_more"] and forward.button("Next page"):
    st.session_state.browse_offset += PAGE_SIZE
    st.session_state.browse_generation += 1
    st.rerun()

if items:
    opened = st.selectbox(
        "Open",
        options=["", *(item["id"] for item in items)],
        format_func=lambda value: value[:8] if value else "(pick one)",
        key=f"opened-{generation}",
    )
    if opened:
        try:
            asset = client.asset(opened)
        except ServiceError as error:
            refused(error)
        else:
            st.subheader(asset["original_filename"] or asset["id"])
            st.image(address_of(asset["links"]["file"]))
            st.write("**Indexing**", asset["index_status"] or "no work yet")
            st.write("**Tags**", asset["tags"] or "none")
            st.json(asset["meta"])
            sure = st.checkbox("I want to delete this picture", key=f"sure-{generation}-{opened}")
            if sure and st.button("Delete", type="primary"):
                try:
                    client.delete(opened)
                except ServiceError as error:
                    refused(error)
                else:
                    # Everything on screen was drawn before the deletion, so the
                    # page is rebuilt rather than patched: a new generation of
                    # widgets, and the listing fetched again.
                    st.session_state.deleted = opened
                    st.session_state.browse_generation += 1
                    st.rerun()

if st.session_state.pop("deleted", None):
    st.success("Deleted. It is gone from the store and from disk.")

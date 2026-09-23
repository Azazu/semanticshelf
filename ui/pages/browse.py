"""Browse: what the store holds, and everything it knows about one picture."""

import streamlit as st

from ui.client import ServiceError, address_of
from ui.shell import refused, service, thumbnails

PAGE_SIZE = 12

st.title("Browse")
st.caption("Everything stored, newest first. Pick a tag to narrow it, or a picture to open it.")

if "browse_offset" not in st.session_state:
    st.session_state.browse_offset = 0
    st.session_state.opened = None

client = service()

try:
    census = client.tags()["items"]
except ServiceError as error:
    refused(error)
    census = []

chosen = st.selectbox(
    "Tag",
    options=["(any)"] + [f"{entry['tag']} ({entry['assets']})" for entry in census],
    index=0,
)
tag = None if chosen == "(any)" else chosen.rsplit(" (", 1)[0]

try:
    page = client.assets(limit=PAGE_SIZE, offset=st.session_state.browse_offset, tags_all=tag)
except ServiceError as error:
    refused(error)
    page = {"items": [], "has_more": False}

items = page["items"]
if not items:
    st.info("Nothing here yet. `make demo` fills the store with a corpus to look at.")
else:
    st.write(f"Showing {len(items)} — narrowed by **{tag}**." if tag else f"Showing {len(items)}.")
    thumbnails(items)
    opened = st.selectbox(
        "Open",
        options=[""] + [item["id"] for item in items],
        format_func=lambda value: value[:8] if value else "(pick one)",
    )
    if page["has_more"] and st.button("Next page"):
        st.session_state.browse_offset += PAGE_SIZE
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
            if st.checkbox("I want to delete this picture", key=f"sure-{opened}"):
                if st.button("Delete", type="primary"):
                    try:
                        client.delete(opened)
                    except ServiceError as error:
                        refused(error)
                    else:
                        st.success("Deleted. It is gone from the store and from disk.")
                        st.session_state.opened = None

"""Upload: a picture, its tags and its metadata, and what the service made of it."""

import streamlit as st

from ui.client import ServiceError, address_of
from ui.shell import refused, service

st.title("Upload")
st.caption("The service decides what a file is from its bytes, not from its name.")

picture = st.file_uploader("Picture", type=["png", "jpg", "jpeg", "webp"])
tags = st.text_input("Tags", placeholder="comma,separated")
meta = st.text_area("Metadata", placeholder='{"origin": "handbook"}', height=80)

if st.button("Upload", type="primary", disabled=picture is None) and picture is not None:
    try:
        created = service().upload(
            name=picture.name,
            data=picture.getvalue(),
            content_type=picture.type or "application/octet-stream",
            tags=tags,
            meta=meta,
        )
    except ServiceError as error:
        refused(error)
    else:
        st.success(f"Stored as {created['id']}.")
        # The one picture in the interface with no "Find similar" under it, and
        # deliberately: its vectors are queued, not computed, so the question
        # would be answered with "nothing is known about what it looks like"
        # for as long as the runner takes. Browse and Search offer it once the
        # work has run.
        st.image(address_of(created["links"]["thumbnail"]))
        st.write("**Indexing**", created["index_status"] or "queued")
        st.json(created)

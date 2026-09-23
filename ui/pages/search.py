"""Search: a description in, pictures out, with the score the service gave."""

import streamlit as st

from ui.client import ServiceError
from ui.shell import asset_caption, refused, service, thumbnails

PAGE_SIZE = 12

st.title("Search")
st.caption("Describe a picture. The service ranks what it has by how near it is to your words.")

if "results" not in st.session_state:
    st.session_state.results = []
    st.session_state.offset = 0
    st.session_state.has_more = False
    st.session_state.model = ""

query = st.text_input("What are you looking for?", key="query")
minimum = st.slider("Minimum score", min_value=-1.0, max_value=1.0, value=0.0, step=0.01)
tag = st.text_input("Only pictures tagged", key="tag", placeholder="optional")

if st.button("Search", type="primary") and query:
    st.session_state.results = []
    st.session_state.offset = 0
    try:
        page = service().search(
            query, limit=PAGE_SIZE, offset=0, min_score=minimum, tag=tag or None
        )
    except ServiceError as error:
        refused(error)
    else:
        st.session_state.results = page["items"]
        st.session_state.offset = page["limit"]
        st.session_state.has_more = page["has_more"]
        st.session_state.model = page["model"]
        if page["query_truncated"]:
            st.warning("The model could not take the whole query and used as much as it could.")

results = st.session_state.results
if results:
    st.write(f"Ranked by **{st.session_state.model}** — a score is comparable only within it.")
    thumbnails(results, captions=[asset_caption(item) for item in results])
    if st.session_state.has_more and st.button("More"):
        try:
            page = service().search(
                st.session_state.query,
                limit=PAGE_SIZE,
                offset=st.session_state.offset,
                min_score=minimum,
                tag=tag or None,
            )
        except ServiceError as error:
            refused(error)
        else:
            st.session_state.results = results + page["items"]
            st.session_state.offset += page["limit"]
            st.session_state.has_more = page["has_more"]
elif st.session_state.get("query"):
    st.info("Nothing matched. A threshold that is too high empties a page, so try lowering it.")

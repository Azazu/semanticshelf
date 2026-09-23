"""Search: a description in, pictures out, with the score the service gave.

Streamlit runs this file top to bottom on every interaction, so what is drawn
is whatever the state says at that moment. Two rules follow, and both were
learned the hard way at Gate 2:

- a click changes state and then reruns — writing state after the page has been
  drawn shows the change one interaction late;
- state is replaced only once a request has succeeded, so a refusal costs the
  refused request and not the results a person already had.
"""

import streamlit as st

from ui.client import ServiceError
from ui.shell import asset_caption, refused, service, thumbnails, without_repeats

PAGE_SIZE = 12

#: What was asked, kept beside what came back: paging must repeat the *search
#: that produced these results*, not whatever the boxes say now.
BLANK: dict[str, object] = {
    "asked": None,
    "results": [],
    "offset": 0,
    "has_more": False,
    "model": "",
    "truncated": False,
    "scan_limited": False,
}
for key, value in BLANK.items():
    st.session_state.setdefault(key, value)

st.title("Search")
st.caption("Describe a picture. The service ranks what it has by how near it is to your words.")

query = st.text_input("What are you looking for?", key="query")
minimum = st.slider("Minimum score", min_value=-1.0, max_value=1.0, value=0.0, step=0.01)
#: Part of the search, not of the page: the service ranks only what carries it.
tag = st.text_input("Only pictures tagged", key="tag", placeholder="optional")

if st.button("Search", type="primary") and query:
    asked = {"query": query, "min_score": minimum, "tag": tag or None}
    try:
        page = service().search(
            query, limit=PAGE_SIZE, offset=0, min_score=minimum, tag=tag or None
        )
    except ServiceError as error:
        refused(error)  # what was found before is still on the page
    else:
        st.session_state.update(
            asked=asked,
            results=page["items"],
            offset=page["limit"],
            has_more=page["has_more"],
            model=page["model"],
            truncated=page["query_truncated"],
            scan_limited=page.get("scan_limited", False),
        )
        st.rerun()

asked = st.session_state.asked
if asked is not None:
    results = st.session_state.results
    if st.session_state.truncated:
        st.warning("The model could not take the whole query and used as much as it could.")
    st.write(f"Ranked by **{st.session_state.model}** — a score is comparable only within it.")

    if st.session_state.scan_limited:
        st.warning(
            "The service stopped at how far it may look before it had filled the page. "
            "There may be more matches further down the ranking — narrow the search further, "
            "or raise the threshold."
        )

    if results:
        thumbnails(results, captions=[asset_caption(item) for item in results])
    elif asked["tag"]:
        st.info(
            f"Nothing the service reached carries **{asked['tag']}**. The tag is part of the "
            "search, so this is the ranking narrowed to that tag — ask for more, or search "
            "without it."
        )
    else:
        st.info("Nothing matched. A threshold that is too high empties a page, so try lowering it.")

    # Outside the `if results` above on purpose: a narrowed page can come back
    # empty while the ranking still has more to give.
    if st.session_state.has_more and st.button("More"):
        try:
            page = service().search(
                asked["query"],
                limit=PAGE_SIZE,
                offset=st.session_state.offset,
                min_score=asked["min_score"],
                tag=asked["tag"],
            )
        except ServiceError as error:
            refused(error)
        else:
            # Without the drop, an asset the service repeats between pages —
            # which it is allowed to do — would be drawn twice, and two
            # thumbnails claiming one widget key stop the page rendering.
            st.session_state.results = without_repeats(results, page["items"])
            st.session_state.offset += page["limit"]
            st.session_state.has_more = page["has_more"]
            st.session_state.scan_limited = page.get("scan_limited", False)
            st.rerun()

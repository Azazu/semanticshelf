"""Find similar: a picture in, the pictures that look like it out.

The other half of the demo. Search asks what a picture is *about* and answers
with CLIP; this asks what one *looks like* and answers with DINOv2, and the two
scores mean nothing against each other — which the page says rather than leaves
to be discovered.

Two ways to ask, one answer: a picture uploaded here, or a picture the store
already holds, reached by the action under any thumbnail in the interface. The
same rules as the search page, learned at its Gate 2: a click changes state and
reruns rather than drawing and then changing, and state is replaced only once a
request has succeeded, so a refusal costs the refused request and not the
results a person already had.
"""

from typing import Any

import streamlit as st

from ui.client import ServiceError
from ui.shell import SIMILAR_ASKED, asset_caption, refused, service, thumbnails

PAGE_SIZE = 12

#: What was asked, beside what came back: paging must repeat *this* question.
BLANK: dict[str, object] = {
    "similar_asked": None,
    "similar_results": [],
    "similar_offset": 0,
    "similar_has_more": False,
    "similar_model": "",
}
for key, value in BLANK.items():
    st.session_state.setdefault(key, value)


def fetch(asked: dict[str, Any], *, offset: int) -> dict[str, Any]:
    """One page of the answer to `asked`, whichever kind of question it is."""
    if asked["kind"] == "asset":
        return service().similar(
            asked["id"], limit=PAGE_SIZE, offset=offset, min_score=asked["min_score"]
        )
    return service().search_image(
        name=asked["name"],
        data=asked["data"],
        content_type=asked["content_type"],
        limit=PAGE_SIZE,
        offset=offset,
        min_score=asked["min_score"],
    )


def ask(asked: dict[str, Any]) -> None:
    """Ask, and if the service answers, show that answer from the top."""
    try:
        page = fetch(asked, offset=0)
    except ServiceError as error:
        refused(error)  # what was found before is still on the page
        return
    st.session_state.update(
        similar_asked=asked,
        similar_results=page["items"],
        similar_offset=page["limit"],
        similar_has_more=page["has_more"],
        similar_model=page["model"],
    )
    st.rerun()


st.title("Find similar")
st.caption(
    "Upload a picture, or use **Find similar** under any thumbnail. "
    "This ranks by appearance, not by subject — and a score here is not "
    "comparable with a score from the search page."
)

# An asset arrived from another page's action. It is consumed before anything is
# drawn, so the answer is on screen in the same run rather than one late.
pending = st.session_state.pop(SIMILAR_ASKED, None)
if pending is not None:
    ask({"kind": "asset", "id": pending, "min_score": None})

picture = st.file_uploader(
    "A picture to look for", type=["png", "jpg", "jpeg", "webp"], key="similar_file"
)
minimum = st.slider("Minimum score", min_value=-1.0, max_value=1.0, value=0.0, step=0.01)

if st.button("Search by picture", type="primary"):
    if picture is None:
        st.info("Choose a picture first, or use **Find similar** under a thumbnail.")
    else:
        ask(
            {
                "kind": "picture",
                "name": picture.name,
                "data": picture.getvalue(),
                "content_type": picture.type or "application/octet-stream",
                "min_score": minimum,
            }
        )

asked = st.session_state.similar_asked
if asked is not None:
    results = st.session_state.similar_results
    if asked["kind"] == "asset":
        st.write(f"Like the picture **{asked['id'][:8]}**, which is not among its own neighbours.")
    else:
        st.write(f"Like **{asked['name']}**, which was not stored.")
    st.write(
        f"Ranked by **{st.session_state.similar_model}** — a score is comparable only within it."
    )

    if results:
        thumbnails(
            results,
            captions=[asset_caption(item) for item in results],
            # Asking about a neighbour is a new question on this same page, so
            # it replaces the state and reruns instead of navigating here again.
            on_similar=lambda asset_id: ask({"kind": "asset", "id": asset_id, "min_score": None}),
        )
    else:
        st.info(
            "Nothing came back. A threshold that is too high empties a page, and a store "
            "with no vectors of this model has nothing to rank — `semanticshelf index missing` "
            "fills those in."
        )

    if st.session_state.similar_has_more and st.button("More"):
        try:
            page = fetch(asked, offset=st.session_state.similar_offset)
        except ServiceError as error:
            refused(error)
        else:
            st.session_state.similar_results = results + page["items"]
            st.session_state.similar_offset += page["limit"]
            st.session_state.similar_has_more = page["has_more"]
            st.rerun()

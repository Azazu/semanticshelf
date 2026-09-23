"""The demo interface: four pages over the service's HTTP API.

Run it with `make ui`. It needs nothing but the address of the service
(`API_BASE_URL`), and it can reach nothing else: no database, no media root, no
model — a test walks these modules' imports and proves it.
"""

import streamlit as st

PAGES = [
    st.Page("pages/search.py", title="Search", icon=":material/search:", default=True),
    st.Page("pages/browse.py", title="Browse", icon=":material/photo_library:"),
    st.Page("pages/upload.py", title="Upload", icon=":material/upload:"),
    st.Page("pages/status.py", title="Status", icon=":material/monitor_heart:"),
]

st.set_page_config(page_title="SemanticShelf", layout="wide")
st.navigation(PAGES).run()

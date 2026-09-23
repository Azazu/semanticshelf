"""Status: whether the service is ready, what it holds, and what it still owes."""

import streamlit as st

from ui.client import ServiceError
from ui.shell import refused, service

st.title("Status")
st.caption("Readiness as the probe answers it, and the store's own counters.")

client = service()

st.subheader("Ready")
try:
    ready = client.ready()
except ServiceError as error:
    refused(error)
else:
    st.success(f"{ready['status']}")
    st.table({"check": list(ready["checks"]), "outcome": list(ready["checks"].values())})

st.subheader("What is stored")
try:
    stats = client.stats()
except ServiceError as error:
    refused(error)
else:
    left, right = st.columns(2)
    left.metric("Assets", stats["assets"])
    right.metric("Stored bytes", f"{stats['stored_bytes']:,}")
    if stats["work"]:
        st.table(
            {
                "model": [entry["model"] for entry in stats["work"]],
                "state": [entry["status"] for entry in stats["work"]],
                "jobs": [entry["jobs"] for entry in stats["work"]],
            }
        )
    else:
        st.info("No indexing work at all — nothing has been stored yet.")
    waiting = stats["oldest_waiting_seconds"]
    if waiting is None:
        st.write("**Nothing is waiting.**")
    else:
        st.write(f"**The oldest waiting work has waited {waiting:.0f} seconds.**")

import os
from pathlib import Path
from typing import Dict, Any, Optional

import streamlit as st

from general_user import general_user_dashboard as music_therapy_dashboard
from caregiver import caregiver_dashboard as ml_caregiver_dashboard
from db import DDB


# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(
    page_title="NeuroHarmony",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------
# Global styles (lilac theme + header recolor + spacing fixes)
# -----------------------------
st.markdown(
    """
    <style>
      /* App background */
      .stApp { background-color: #E6E6FA; }

      /* Recolor Streamlit header (remove white strip and shadow) */
      [data-testid="stHeader"] {
        background-color: #E6E6FA !important;
        box-shadow: none !important;
      }

      /* Some builds show a thin white decoration under header */
      [data-testid="stDecoration"] { background: transparent !important; }

      /* Optional: also make the toolbar transparent */
      [data-testid="stToolbar"] { background: transparent !important; }

      /* Reduce top padding so content sits closer to header */
      main .block-container { padding-top: 0.6rem; }
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Simple role config
# -----------------------------
CAREGIVER_EMAILS = [
    "hannahsundar2009@gmail.com"
]

def is_caregiver(email: str) -> bool:
    return email.lower() in [e.lower() for e in CAREGIVER_EMAILS]

# -----------------------------
# Auth helper
# -----------------------------
def get_user_simple() -> Optional[Dict[str, Any]]:
    exp_user = getattr(st, "experimental_user", None)
    has_login = hasattr(st, "login") and hasattr(st, "logout")

    if exp_user is not None and hasattr(exp_user, "is_logged_in") and has_login:
        with st.sidebar:
            if not exp_user.is_logged_in:
                if st.button("Log in with Google", type="primary"):
                    st.login()
                return None
            else:
                if st.button("Log out", type="secondary"):
                    st.logout()
                    return None

        name = getattr(exp_user, "name", None) or getattr(exp_user, "username", None) or "User"
        email = getattr(exp_user, "email", None) or ""
        st.markdown(
            f"Hello, <span style='color: orange; font-weight: bold;'>{name}</span>!",
            unsafe_allow_html=True
        )
        return {"name": name, "email": email}

    # If experimental auth isn't available, treat as not logged in
    return None

# -----------------------------
# Main
# -----------------------------
def main():
    # --- Centered logo at the top ---
    app_dir = Path(__file__).parent
    logo_path = app_dir / "neuroharmony.png"  # ensure the file is next to main.py

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        # Adjust width as you prefer (e.g., 220–360)
        st.image(str(logo_path), caption="EEG Frequency Bands", width=500)
    st.markdown("---")

    # --- Authenticate ---
    user = get_user_simple()
    if not user:
        st.stop()
    st.session_state.user_info = user

    # --- Persist user + login event ---
    email = (user.get("email") or "").strip()
    name = (user.get("name") or "User").strip()
    if email:
        ddb = DDB()
        _ = ddb.upsert_user(email, name)
        _ = ddb.log_event(email, "login", {})

    # --- One-time seed for songs collection if empty ---
    if not st.session_state.get("_seed_done"):
        try:
            ddb_seed = DDB()
            has_any = len(ddb_seed.list_songs(limit=1)) > 0
            if not has_any:
                _ = ddb_seed.seed_initial_songs()
        except Exception:
            pass
        finally:
            st.session_state["_seed_done"] = True

    # --- Route by role ---
    user_email = (user.get("email") or "").strip()
    if user_email and is_caregiver(user_email):
        ml_caregiver_dashboard()
    else:
        music_therapy_dashboard()


if __name__ == "__main__":
    main()

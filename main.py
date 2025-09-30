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
    initial_sidebar_state="expanded",
)

# -----------------------------
# Global styles (lilac theme + sane layout)
# -----------------------------
st.markdown(
    """
    <style>
      /* App background */
      .stApp { background-color: #E6E6FA; }

      /* Header: match background, remove shadow/gap */
      [data-testid="stHeader"], [data-testid="stToolbar"] {
        background-color: #E6E6FA !important;
        box-shadow: none !important;
      }
      [data-testid="stDecoration"] { background: transparent !important; }

      /* Sidebar: same lilac; let dashboards add their own headings */
      [data-testid="stSidebar"] {
        background-color: #E6E6FA !important;
        border-right: 0;
      }
      [data-testid="stSidebar"] * { color: #222 !important; }

      /* Bring content closer to header and control width for nicer line length */
      main .block-container {
        padding-top: 0.6rem;
        max-width: 1180px;
      }

      /* Make buttons a bit softer */
      .stButton>button { border-radius: 10px !important; }

      /* Center helper */
      .nh-center { text-align: center; }

      /* Small, subtle tagline */
      .nh-tagline {
        color: #4a4a4a;
        font-size: 15px;
        margin-top: 8px;
      }

      /* Simple divider with sensible spacing */
      .nh-divider { margin: 12px 0 18px 0; border: none; height: 1px; background: rgba(0,0,0,0.08); }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Simple role config
# -----------------------------
CAREGIVER_EMAILS = [
    "hannahsundar2009@gmail.com"
]

def is_caregiver(email: str) -> bool:
    return email.lower() in (e.lower() for e in CAREGIVER_EMAILS)

# -----------------------------
# Auth helper (no sidebar headings here!)
# -----------------------------
def get_user_simple() -> Optional[Dict[str, Any]]:
    exp_user = getattr(st, "experimental_user", None)
    has_login = hasattr(st, "login") and hasattr(st, "logout")

    # Put ONLY login/logout in sidebar; dashboards own the rest.
    with st.sidebar:
        if exp_user is not None and hasattr(exp_user, "is_logged_in") and has_login:
            if not exp_user.is_logged_in:
                if st.button("Log in with Google", type="primary", use_container_width=True):
                    st.login()
                return None
            else:
                if st.button("Log out", type="secondary", use_container_width=True):
                    st.logout()
                    return None
        else:
            st.info("Sign-in not available in this environment.")
            return None

    # If we get here, user is logged in
    name = getattr(exp_user, "name", None) or getattr(exp_user, "username", None) or "User"
    email = getattr(exp_user, "email", None) or ""
    return {"name": name, "email": email}

# -----------------------------
# Hero (simple, no card/shadow)
# -----------------------------
def hero_block(user_name: str):
    app_dir = Path(__file__).parent
    logo_path = app_dir / "neuroharmony.png"  # ensure file exists

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown('<div class="nh-center">', unsafe_allow_html=True)
        st.image(str(logo_path), width=420)
        st.markdown(
            f"<div class='nh-tagline'>Hello, <b>{user_name}</b> — personalized music for mind & wellness</div>",
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="nh-divider"></div>', unsafe_allow_html=True)

# -----------------------------
# Main
# -----------------------------
def main():
    # --- Authenticate ---
    user = get_user_simple()
    if not user:
        st.stop()
    st.session_state.user_info = user

    # --- Persist user + login event ---
    email = (user.get("email") or "").strip()
    name = (user.get("name") or "User").strip()
    if email:
        try:
            ddb = DDB()
            _ = ddb.upsert_user(email, name)
            _ = ddb.log_event(email, "login", {})
        except Exception:
            pass  # don't block UI if DB is down

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

    # --- Brand hero once, then let dashboard handle page & sidebar sections ---
    hero_block(user_name=name)

    # IMPORTANT: Do NOT create any sidebar sections here.
    # Your dashboards (general_user / caregiver) should render:
    # - Navigation (selectbox)
    # - Quick Controls (Stop, Now Playing, etc.)
    # This prevents duplicates.

    if email and is_caregiver(email):
        ml_caregiver_dashboard()
    else:
        music_therapy_dashboard()

if __name__ == "__main__":
    main()

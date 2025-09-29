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
# Global styles (theme + header + hero polish)
# -----------------------------
st.markdown(
    """
    <style>
      /* App background */
      .stApp { background-color: #E6E6FA; }

      /* Header to lilac, remove shadow/gap */
      [data-testid="stHeader"],
      [data-testid="stToolbar"] {
        background-color: #E6E6FA !important;
        box-shadow: none !important;
      }
      [data-testid="stDecoration"] { background: transparent !important; }

      /* Bring content closer to header */
      main .block-container { padding-top: 0.6rem; }

      /* --- HERO STYLES --- */
      .hero-wrap {
        margin: 8px 0 24px 0;
      }
      .hero-card {
        background: #F2F0FF;           /* very light lilac for contrast */
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 18px;
        padding: 28px 28px 22px;
      }
      .hero-title {
        margin: 0 0 10px 0;
        font-size: 48px;
        line-height: 1.1;
      }
      .hero-sub {
        margin: 0;
        font-size: 18px;
        color: #333;
        line-height: 1.6;
      }
      /* Limit hero image and add soft style */
      .hero-img img {
        max-width: 520px;
        width: 100%;
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.10);
      }

      /* Mobile stacking tweaks */
      @media (max-width: 1000px) {
        .hero-title { font-size: 36px; }
        .hero-sub   { font-size: 16px; }
      }
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
# HERO (text left, image right)
# -----------------------------
def hero(img_path_or_url: str):
    st.markdown('<div class="hero-wrap"></div>', unsafe_allow_html=True)
    left, right = st.columns([7, 5], gap="large")

    with left:
        st.markdown(
            """
            <div class="hero-card">
              <h1 class="hero-title">NeuroHarmony</h1>
              <p class="hero-sub">
                EEG-guided music therapy: upload EEG sessions, predict genre affinity,
                and generate engagement &amp; focus scores to personalize listening plans.
              </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    with right:
        # use_container_width avoids the deprecation warning
        st.markdown('<div class="hero-img">', unsafe_allow_html=True)
        st.image(img_path_or_url, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


# -----------------------------
# Main
# -----------------------------
def main():
    # --- HERO at the top ---
    app_dir = Path(__file__).parent
    HERO_IMAGE = str(app_dir / "neuroharmony.png")  # ensure the file exists next to main.py
    hero(HERO_IMAGE)
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

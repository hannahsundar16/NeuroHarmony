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
# Global styles (theme + header + layout polish)
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

      /* Constrain content width for nicer readability on big screens */
      main .block-container { 
        padding-top: 0.8rem; 
        max-width: 1200px;         /* <<< tweak page width here */
      }

      /* Sidebar subtle tint */
      [data-testid="stSidebar"] {
        background: #f4f2ff;
      }

      /* --- HERO STYLES --- */
      .nh-hero-row {
        display: flex; 
        gap: 28px;
        align-items: center;       /* vertical center title + image */
      }
      @media (max-width: 1000px){
        .nh-hero-row { flex-direction: column; }
      }

      .nh-hero-left {
        flex: 0 1 58%;
      }
      .nh-hero-right {
        flex: 0 1 42%;
        display: flex;
        justify-content: center;
      }

      .nh-card {
        background: #F2F0FF;       /* very light lilac */
        border: 1px solid rgba(0,0,0,0.06);
        border-radius: 18px;
        padding: 26px 26px 20px;
      }

      .nh-title {
        margin: 0 0 12px 0;
        font-size: 56px;
        line-height: 1.06;
        letter-spacing: -0.5px;
      }
      .nh-sub {
        margin: 0;
        font-size: 20px;
        color: #2f2f2f;
        line-height: 1.65;
        max-width: 720px;          /* keep lines readable */
      }

      .nh-img {
        width: 100%;
        max-width: 560px;
        border-radius: 16px;
        box-shadow: 0 8px 22px rgba(0,0,0,0.12);
      }
      .nh-caption {
        text-align: center;
        font-size: 14px;
        color: #666;
        margin-top: 8px;
      }

      /* Buttons row (optional) */
      .nh-cta { margin-top: 14px; }
      .nh-cta > div { display: inline-block; margin-right: 10px; }

      @media (max-width: 1000px){
        .nh-title { font-size: 40px; }
        .nh-sub   { font-size: 18px; }
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

    return None


# -----------------------------
# HERO (custom flex layout: text left, image right)
# -----------------------------
def hero(img_path_or_url: str):
    # Build hero with pure HTML/CSS for perfect alignment/centering
    st.markdown(
        f"""
        <div class="nh-hero-row">
          <div class="nh-hero-left">
            <div class="nh-card">
              <h1 class="nh-title">NeuroHarmony</h1>
              <p class="nh-sub">
                EEG-guided music therapy: upload EEG sessions, predict genre affinity,
                and generate engagement &amp; focus scores to personalize listening plans.
              </p>
              <!-- Optional CTAs:
              <div class="nh-cta">
                <div><a href="#upload" class="stButton"><button>Upload EEG CSV</button></a></div>
                <div><a href="#analytics" class="stButton"><button>View Analytics</button></a></div>
              </div>
              -->
            </div>
          </div>
          <div class="nh-hero-right">
            <div>
              <img class="nh-img" src="{img_path_or_url}" alt="NeuroHarmony Illustration"/>
              <div class="nh-caption">EEG Frequency Bands (Delta, Theta, Alpha, Beta, Gamma)</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# -----------------------------
# Main
# -----------------------------
def main():
    # --- HERO at the top ---
    app_dir = Path(__file__).parent
    HERO_IMAGE = str("neuroharmony.png")  # or a URL
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

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
# Global styles (lilac theme + sane layout + hero blurb)
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

      /* Sidebar: lilac background */
      [data-testid="stSidebar"] {
        background-color: #E6E6FA !important;
        border-right: 0;
      }
      [data-testid="stSidebar"] * { color: #222 !important; }

      /* Content width & padding */
      main .block-container {
        padding-top: 0.6rem;
        max-width: 1180px;
      }

      /* Buttons */
      .stButton>button { border-radius: 10px !important; }

      /* Hero blurb styles */
      body, .stApp, .markdown-text-container {
        font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
      }
      .nh-hero-wrap {
        display: flex; align-items: center; justify-content: center; gap: 44px;
        margin: 10px 0 20px 0; flex-wrap: wrap;
      }
      .nh-hero-left { max-width: 620px; }
      .nh-hero-title {
        font-size: 44px; line-height: 1.15; font-weight: 800; margin: 0 0 12px 0;
        letter-spacing: -0.5px; color: #212529;
      }
      .nh-hero-copy {
        font-size: 18px; line-height: 1.65; color: #3f3f46; margin: 0 0 6px 0;
      }
      .nh-hero-caption {
        font-size: 14px; color: #6b7280; margin-top: 8px;
      }
      .nh-hero-img {
        border-radius: 14px;
        box-shadow: 0 4px 22px rgba(26, 20, 90, 0.06);
      }

      .nh-divider { margin: 16px 0 22px 0; border: none; height: 1px; background: rgba(0,0,0,0.08); }
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
# Auth helper
# -----------------------------
def get_user_simple() -> Optional[Dict[str, Any]]:
    exp_user = getattr(st, "experimental_user", None)
    has_login = hasattr(st, "login") and hasattr(st, "logout")

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

    name = getattr(exp_user, "name", None) or getattr(exp_user, "username", None) or "User"
    email = getattr(exp_user, "email", None) or ""
    return {"name": name, "email": email}

# -----------------------------
# Hero blurb
# -----------------------------
def hero_block(user_name: str):
    app_dir = Path(__file__).parent
    # Swap this illustration with your own if available
    illo_path = app_dir / "hero_illustration.png"
    logo_path = app_dir / "neuroharmony.png"
    img_path = str(illo_path if illo_path.exists() else logo_path)

    st.markdown(
        f"""
        <div class="nh-hero-wrap">
          <div class="nh-hero-left">
            <h1 class="nh-hero-title">NeuroHarmony</h1>
            <p class="nh-hero-copy">
              EEG-guided music therapy: upload EEG sessions, predict genre affinity,
              and generate engagement &amp; focus scores to personalize listening plans.
            </p>
            <div class="nh-hero-caption">
              Hello, <b>{user_name}</b> — personalized music for mind &amp; wellness<br/>
              <span style="opacity:.9;">EEG Frequency Bands (Delta, Theta, Alpha, Beta, Gamma)</span>
            </div>
          </div>
          <div>
            <img src="file://{img_path}" alt="Brain & music illustration"
                 width="360" class="nh-hero-img"/>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            pass

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

    # --- Hero blurb ---
    hero_block(user_name=name)

    # --- Route to dashboards ---
    if email and is_caregiver(email):
        ml_caregiver_dashboard()
    else:
        music_therapy_dashboard()

if __name__ == "__main__":
    main()

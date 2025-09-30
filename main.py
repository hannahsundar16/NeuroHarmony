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
# Global styles (lilac theme + polish)
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

      /* Sidebar: same lilac + better contrast for text/icons */
      [data-testid="stSidebar"] {
        background-color: #E6E6FA !important;
        border-right: 0;
      }
      [data-testid="stSidebar"] * { color: #222 !important; }

      /* Bring content closer to header */
      main .block-container { padding-top: 0.6rem; }

      /* Subtle card utility class (for hero wrapper if you want) */
      .nh-card {
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 6px 24px rgba(18, 16, 99, 0.06);
        padding: 18px 20px;
      }

      /* Center utilities */
      .nh-center { text-align: center; }

      /* Tiny subtitle */
      .nh-subtle {
        color: #4a4a4a;
        font-size: 15px;
        margin-top: 8px;
      }

      /* Divider spacing tweak */
      .nh-divider { margin: 16px 0 24px 0; border: none; height: 1px; background: rgba(0,0,0,0.08); }

      /* Buttons look a bit crisper on lilac */
      .stButton>button {
        border-radius: 12px !important;
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

    with st.sidebar:
        st.markdown("## 🎵 Navigation")

        if exp_user is not None and hasattr(exp_user, "is_logged_in") and has_login:
            if not exp_user.is_logged_in:
                if st.button("Log in with Google", type="primary"):
                    st.login()
                return None
            else:
                # Show a compact logout at top of sidebar
                if st.button("Log out", type="secondary"):
                    st.logout()
                    return None
        else:
            # If experimental auth isn't available, treat as not logged in
            st.info("Sign-in not available in this environment.")
            return None

        st.markdown("---")
        st.markdown("## 🎛️ Quick Controls")

    # If we get here, user is logged in
    name = getattr(exp_user, "name", None) or getattr(exp_user, "username", None) or "User"
    email = getattr(exp_user, "email", None) or ""
    return {"name": name, "email": email}


# -----------------------------
# Hero (brand once, friendly)
# -----------------------------
def hero_block(user_name: str):
    app_dir = Path(__file__).parent
    logo_path = app_dir / "neuroharmony.png"  # ensure file exists next to this script

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown('<div class="nh-card nh-center">', unsafe_allow_html=True)
        # Adjust width to your liking (e.g., 220–360)
        st.image(str(logo_path), width=420, caption=None)
        st.markdown(
            f"""
            <div class="nh-subtle">Hello, <b>{user_name}</b> — personalized music for mind & wellness</div>
            """,
            unsafe_allow_html=True
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
            # Fail silently if DB unavailable; app should still work
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

    # --- Brand hero once, then route ---
    hero_block(user_name=name)

    # --- Route by role ---
    user_email = email
    if user_email and is_caregiver(user_email):
        ml_caregiver_dashboard()   # Caregiver view (no extra branding here)
    else:
        music_therapy_dashboard()  # General user view (titles/sections inside module)


if __name__ == "__main__":
    main()

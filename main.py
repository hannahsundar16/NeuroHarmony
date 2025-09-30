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
# Global styles (lilac theme + compact headings + hero image crop helper)
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

      /* Product-like font stack + slightly tighter headings */
      body, .stApp, .markdown-text-container {
        font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
      }
      h1, h2, h3 { letter-spacing: -0.2px; }

      /* Divider utility */
      .nh-hr { border: none; height: 1px; background: rgba(0,0,0,.08); margin: 10px 0 18px 0; }

      /* CTA button look for the hero */
      .nh-cta {
        display:inline-block; padding:10px 16px; border-radius:12px;
        background:#4f46e5; color:#fff; text-decoration:none;
        box-shadow:0 4px 12px rgba(79,70,229,.25);
      }
      .nh-cta:hover { filter: brightness(1.05); }

      /* If you keep a PNG with wordmark, this crops the bottom (hiding the text) */
      .nh-crop-box {
        width: 100%;
        height: 320px;             /* visible height */
        overflow: hidden;          /* hide overflow (the wordmark) */
        border-radius: 14px;
        box-shadow: 0 4px 22px rgba(26, 20, 90, 0.06);
        background: #efeafc;
      }
      .nh-crop-box img {
        width: 100%;
        height: 460px;             /* taller than box so bottom gets hidden */
        object-fit: cover;
        object-position: center top; /* keep the headphones/wave */
        display: block;
      }
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
# Auth helper (sidebar shows ONLY login/logout)
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
# Hero blurb (left text + right illustration WITHOUT wordmark)
# -----------------------------
def hero_block(user_name: str):
    """
    Headline is thematic (not brand). Right side uses a text-free inline SVG illustration.
    If you prefer to keep your PNG with wordmark, comment the SVG section and use the
    'cropped image' fallback below.
    """
    app_dir = Path(__file__).parent
    logo_with_text = app_dir / "neuroharmony.png"  # used only for the crop fallback

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown(
            f"""
            <div style="padding-top:8px;">
              <h1 style="
                  margin:0 0 10px 0;
                  font-size:42px;
                  line-height:1.12;
                  letter-spacing:-0.6px;">
                Personalize Your Mind & Music
              </h1>
              <p style="margin:0 0 10px 0; font-size:18px; line-height:1.65; color:#3f3f46;">
                EEG-guided music therapy that learns what works for you: upload EEG sessions,
                predict genre affinity, and generate engagement &amp; focus scores to tailor listening plans.
              </p>
              <div style="font-size:14px; color:#6b7280; margin:8px 0 14px 0;">
                Hello, <b>{user_name}</b> — your wellness journey starts here.
              </div>
              <a class="nh-cta" href="#dashboard-start">Get Started</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        # ---- Preferred: INLINE SVG (no brand text) ----
        svg = """
        <svg width="100%" height="320" viewBox="0 0 400 320" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="g" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stop-color="#6D4AFF"/>
              <stop offset="1" stop-color="#FF7AC6"/>
            </linearGradient>
          </defs>
          <!-- soft card -->
          <rect x="0" y="0" width="400" height="320" rx="14" fill="#F4EEFF"/>
          <!-- headphones -->
          <path d="M80 180 a120 120 0 1 1 240 0 v60 a20 20 0 0 1 -20 20 h-20 a20 20 0 0 1 -20 -20 v-60
                   a80 80 0 1 0 -160 0 v60 a20 20 0 0 1 -20 20 h-20 a20 20 0 0 1 -20 -20 z"
                fill="#5A4FD6"/>
          <!-- waveform -->
          <polyline fill="none" stroke="url(#g)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"
            points="60,190 90,190 115,160 135,210 155,150 175,210 195,170 215,205 235,160 255,195 275,175 295,200 320,185 340,190"/>
        </svg>
        """
        st.markdown(svg, unsafe_allow_html=True)

        # ---- Fallback: CROP your existing PNG to hide the wordmark ----
        # if not logo_with_text.exists():
        #     st.markdown(svg, unsafe_allow_html=True)
        # else:
        #     st.markdown(f'''
        #         <div class="nh-crop-box">
        #             <img src="file://{str(logo_with_text)}" alt="Logo cropped"/>
        #         </div>
        #     ''', unsafe_allow_html=True)

    st.markdown("<div class='nh-hr'></div>", unsafe_allow_html=True)
    st.markdown('<div id="dashboard-start"></div>', unsafe_allow_html=True)

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

    # --- Seed songs once if empty ---
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

    # --- Hero blurb (non-branded art on right) ---
    hero_block(user_name=name)

    # --- Route to dashboards (dashboards own sidebar sections) ---
    if email and is_caregiver(email):
        ml_caregiver_dashboard()
    else:
        music_therapy_dashboard()

if __name__ == "__main__":
    main()

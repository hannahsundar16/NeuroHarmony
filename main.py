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
# Global styles (lilac theme + sane layout + compact headings)
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

    # If we get here, user is logged in
    name = getattr(exp_user, "name", None) or getattr(exp_user, "username", None) or "User"
    email = getattr(exp_user, "email", None) or ""
    return {"name": name, "email": email}

# -----------------------------
# Hero blurb (left text + right illustration; MINIMAL brand mentions)
# -----------------------------
def hero_block(user_name: str):
    """
    Headline is thematic (not brand). Image should be an icon/illustration
    without the word 'NeuroHarmony' to avoid repetition.
    """
    app_dir = Path(__file__).parent
    # Prefer an illustration with NO wordmark; fallbacks ensure something renders.
    # Put a simple headphone/brain-only PNG named 'hero_icon.png' next to this file.
    icon = app_dir / "hero_icon.png"              # <— recommended (no text)
    illo = app_dir / "hero_illustration.png"      # alt illustration (no text)
    logo_wordmark = app_dir / "neuroharmony.png"  # has text; only as last local resort
    fallback_url = "https://raw.githubusercontent.com/encharm/Font-Awesome-SVG-PNG/master/black/png/512/headphones.png"

    img_src = None
    for p in (icon, illo, logo_wordmark):
        if p.exists():
            img_src = str(p)
            break

    # 60 / 40 split like your reference
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
                EEG-guided music therapy that learns what works for you:
                upload EEG sessions, predict genre affinity, and generate
                engagement & focus scores to tailor listening plans.
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
        if img_src:
            st.image(img_src, use_container_width=True)
        else:
            st.image(fallback_url, width=260)

    st.markdown("<div class='nh-hr'></div>", unsafe_allow_html=True)
    # Anchor so the CTA can scroll here or the next section
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
            # Don't block UI if DB is unavailable
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

    # --- Hero blurb (non-branded headline) ---
    hero_block(user_name=name)

    # --- Route to dashboards (dashboards own sidebar sections) ---
    if email and is_caregiver(email):
        ml_caregiver_dashboard()
    else:
        music_therapy_dashboard()

if __name__ == "__main__":
    main()

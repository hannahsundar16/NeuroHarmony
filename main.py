import streamlit as st
from typing import Dict, Any, Optional
from general_user import general_user_dashboard as music_therapy_dashboard
from caregiver import caregiver_dashboard as ml_caregiver_dashboard
import os
from db import DDB


st.set_page_config(
    page_title="NeuroHarmony",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        .stApp {
            background-color: #E6E6FA; /* Light Lilac (Lavender) */
        }
    </style>
    """,
    unsafe_allow_html=True
)




#IMAGE_ADDRESS = "https://www.denvercenter.org/wp-content/uploads/2024/10/music-therapy.jpg"

CAREGIVER_EMAILS = [
    "hannahsundar2009@gmail.com"
]

def is_caregiver(email: str) -> bool:
    return email.lower() in [e.lower() for e in CAREGIVER_EMAILS]

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
        st.markdown(f"Hello, <span style='color: orange; font-weight: bold;'>{name}</span>!", unsafe_allow_html=True)
        return {"name": name, "email": email}
    
    return None



def main():    

    # Title and image
   # st.title("NeuroHarmony")
   # st.image(IMAGE_ADDRESS, caption="EEG Frequency Bands (Delta, Theta, Alpha, Beta, Gamma)")
    st.image("neuroharmony.png", caption="EEG Frequency Bands", width=500)
    st.markdown("---")
    # Authenticate
    user = get_user_simple()
    if not user:
        st.stop()
    st.session_state.user_info = user

    # Upsert user and log login to Firestore
    email = (user.get("email") or "").strip()
    name = (user.get("name") or "User").strip()
    if email:
        ddb = DDB()
        ok_user = ddb.upsert_user(email, name)
        ok_log = ddb.log_event(email, 'login', {})
    # One-time automatic seeding: if songs dataset is empty, seed defaults
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
    # Route by role based on email
    user_email = (user.get("email") or "").strip()
    if user_email and is_caregiver(user_email):
        # Caregiver dashboard
        ml_caregiver_dashboard()
    else:
        # General user dashboard
        music_therapy_dashboard()

if __name__ == "__main__":
    main()


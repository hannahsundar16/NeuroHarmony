import time
from typing import Any, Dict, Optional, List

import streamlit as st
import json
from collections.abc import Mapping
from google.cloud import firestore
from google.api_core.exceptions import GoogleAPIError
from google.oauth2 import service_account

"""Firestore configuration using root-level gcp_service_account only.

Required structure in Streamlit Secrets (Cloud UI or local .streamlit/secrets.toml):

gcp_service_account = { ... full service account json ... }

# Optional overrides
[collections]
users = "NeuroTunes_Users"
songs = "NeuroTunes_Songs"
recommendations = "NeuroTunes_Recommendations"
events = "NeuroTunes_Events"

# Optional
debug = true
GCP_PROJECT_ID = "override-project-id-if-needed"  # falls back to SA project_id
"""
def _get_sa_dict() -> Dict[str, Any]:
    """Return service account as dict from st.secrets['gcp_service_account'].

    Accepts either a TOML inline table (already dict) or a JSON string.
    """
    try:
        raw = st.secrets.get("gcp_service_account")
    except Exception:
        raw = None
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    try:
        keys = list(st.secrets.keys())
    except Exception:
        keys = []
    raise RuntimeError(f"Missing or invalid gcp_service_account in Streamlit secrets. Provide as TOML inline table or JSON string. Available sections: {keys}")


def _get_fs_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    # Required: service account
    sa = _get_sa_dict()

    # Project ID: from SA or optional override
    project_id = sa.get("project_id") or st.secrets.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError("Could not determine project_id. Ensure gcp_service_account.project_id or GCP_PROJECT_ID is set.")
    cfg["project_id"] = str(project_id)

    # Collections: optional override via [collections]; else sensible defaults
    col = st.secrets.get("collections")
    defaults = {
        "users": "NeuroTunes_Users",
        "songs": "NeuroTunes_Songs",
        "recommendations": "NeuroTunes_Recommendations",
        "events": "NeuroTunes_Events",
    }
    if isinstance(col, Mapping):
        col = dict(col)
        cfg["users_col"] = str(col.get("users", defaults["users"]))
        cfg["songs_col"] = str(col.get("songs", defaults["songs"]))
        cfg["recs_col"] = str(col.get("recommendations", defaults["recommendations"]))
        cfg["events_col"] = str(col.get("events", defaults["events"]))
    else:
        cfg["users_col"] = defaults["users"]
        cfg["songs_col"] = defaults["songs"]
        cfg["recs_col"] = defaults["recommendations"]
        cfg["events_col"] = defaults["events"]

    cfg["debug"] = bool(st.secrets.get("debug"))
    return cfg


def _ts_ms() -> int:
    return int(time.time() * 1000)


def _credentials_from_secrets(cfg: Dict[str, Any]) -> Optional[service_account.Credentials]:
    """Return Credentials from root-level gcp_service_account if present."""
    try:
        sa = _get_sa_dict()
        # Normalize private key in case it contains literal \n characters
        pk = sa.get("private_key")
        if isinstance(pk, str) and "-----BEGIN" in pk and "\\n" in pk and "\n" not in pk:
            sa = dict(sa)
            sa["private_key"] = pk.replace("\\n", "\n")
        return service_account.Credentials.from_service_account_info(sa)
    except Exception:
        return None


def get_firestore_client() -> firestore.Client:
    """Return a Firestore client built from st.secrets['gcp_service_account'].

    This follows the requested pattern and uses our robust secrets parsing
    that accepts either a TOML inline table or a JSON string.
    """
    sa = _get_sa_dict()
    # Normalize private key newlines for PEM parsing
    pk = sa.get("private_key")
    if isinstance(pk, str) and "-----BEGIN" in pk and "\\n" in pk and "\n" not in pk:
        sa = dict(sa)
        sa["private_key"] = pk.replace("\\n", "\n")
    credentials = service_account.Credentials.from_service_account_info(sa)
    project_id = sa.get("project_id")
    return firestore.Client(credentials=credentials, project=project_id)


class DDB:
    """Firestore-backed helper reusing the existing DDB interface.

    Collections used (names from env above):
    - Users: document id = user_email
    - Songs: document id = song_id
    - Recommendations: document id = user_email
    - Events: auto-id documents with fields {user_email, ts, event_type, payload}
    """

    def __init__(self, project_id: Optional[str] = None):
        # Load configuration from secrets
        cfg = _get_fs_config()
        project = project_id or cfg.get("project_id")
        # Initialize Firestore client using service account credentials when available
        creds = _credentials_from_secrets(cfg)
        if creds is not None:
            self._client = firestore.Client(project=project or getattr(creds, "project_id", None), credentials=creds)
        else:
            # Use ADC with optional project id
            self._client = firestore.Client(project=project) if project else firestore.Client()
        # Collections
        self._users = self._client.collection(cfg["users_col"]) 
        self._songs = self._client.collection(cfg["songs_col"]) 
        self._recs = self._client.collection(cfg["recs_col"]) 
        self._events = self._client.collection(cfg["events_col"]) 
        # Debug flag
        self._debug = bool(cfg.get("debug"))
        # Last error storage for diagnostics
        self._last_error: Optional[str] = None

    def last_error(self) -> Optional[str]:
        return self._last_error

    # Users
    def upsert_user(self, email: str, name: str) -> bool:
        try:
            if not email:
                return False
            doc_ref = self._users.document(email)
            doc_ref.set({
                "user_email": email,
                "name": name or "User",
                "updated_at": _ts_ms(),
            }, merge=True, timeout=30.0)
            return True
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore upsert_user failed: {e}")
            self._last_error = str(e)
            return False

    # Recommendations
    def put_recommendations(self, email: str, categories: List[Dict[str, Any]], cognitive_scores: Optional[Dict[str, Any]]) -> bool:
        try:
            if not email:
                return False
            data: Dict[str, Any] = {
                "user_email": email,
                "updated_at": _ts_ms(),
                "categories": categories or [],
            }
            if cognitive_scores is not None:
                data["cognitive_scores"] = cognitive_scores
            self._recs.document(email).set(data, timeout=30.0)
            return True
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore put_recommendations failed: {e}")
            self._last_error = str(e)
            return False

    def get_recommendations(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            if not email:
                return None
            snap = self._recs.document(email).get(timeout=30.0)
            return snap.to_dict() if snap.exists else None
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore get_recommendations failed: {e}")
            self._last_error = str(e)
            return None

    # Events
    def log_event(self, email: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        try:
            if not email:
                return False
            self._events.add({
                "user_email": email,
                "ts": _ts_ms(),
                "event_type": event_type,
                "payload": payload or {},
            }, timeout=20.0)
            return True
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore log_event failed: {e}")
            self._last_error = str(e)
            return False

    # Songs (optional placeholders)
    def put_song(self, song_id: str, data: Dict[str, Any]) -> bool:
        try:
            if not song_id:
                return False
            self._songs.document(song_id).set({"song_id": song_id, **data}, timeout=30.0)
            return True
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore put_song failed: {e}")
            self._last_error = str(e)
            return False

    def list_songs(self, category: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return songs from Firestore; when category is provided, filter on it.
        Each item includes an 'id' key with the document ID.
        """
        try:
            query = self._songs
            if category:
                query = query.where('category', '==', category)
            # Use a bounded timeout to avoid long hangs
            stream = query.stream(timeout=30.0)
            items: List[Dict[str, Any]] = []
            for doc in stream:
                data = doc.to_dict() or {}
                data.setdefault('song_id', doc.id)
                data.setdefault('id', doc.id)
                items.append(data)
                if limit and len(items) >= limit:
                    break
            return items
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore list_songs failed: {e}")
            self._last_error = str(e)
            return []

    def health_check(self) -> bool:
        """Attempt a lightweight operation to validate Firestore connectivity."""
        try:
            # Try a no-op read on users collection
            _ = self._users.limit(1).stream(timeout=20.0)
            for _doc in _:
                break
            return True
        except GoogleAPIError as e:
            if self._debug:
                st.error(f"Firestore health_check failed: {e}")
            self._last_error = str(e)
            return False

    # -----------------------------
    # Catalog seeding helpers
    # -----------------------------
    @staticmethod
    def _default_audio_url(category: str) -> str:
        urls = {
            "Classical": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
            "Rock": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
            "Pop": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
            "Rap": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
            "R&B": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
        }
        return urls.get(category, urls["Classical"]) 

    def seed_initial_songs(self) -> int:
        """Seed Firestore with a default catalog grouped by category.

        Fields per song: category, song_id, id, name, duration, bpm, key, url.
        Returns the number of songs successfully written.
        """
        catalog = {
            "Classical": [
                {"id": 1, "name": "Bach's Prelude", "duration": 240, "bpm": 72, "key": "C Major"},
                {"id": 2, "name": "Mozart's Sonata", "duration": 280, "bpm": 68, "key": "G Major"},
                {"id": 3, "name": "Beethoven's Symphony", "duration": 320, "bpm": 76, "key": "F Major"},
                {"id": 4, "name": "Chopin's Nocturne", "duration": 200, "bpm": 65, "key": "D Major"},
                {"id": 5, "name": "Vivaldi's Spring", "duration": 260, "bpm": 80, "key": "A Major"},
                {"id": 6, "name": "Debussy's Clair de Lune", "duration": 220, "bpm": 62, "key": "E Major"},
                {"id": 7, "name": "Pachelbel's Canon", "duration": 300, "bpm": 70, "key": "B♭ Major"},
                {"id": 8, "name": "Schubert's Ave Maria", "duration": 180, "bpm": 60, "key": "C Major"},
                {"id": 9, "name": "Brahms' Lullaby", "duration": 160, "bpm": 58, "key": "G Major"}
            ],
            "Rock": [
                {"id": 10, "name": "Thunder Strike", "duration": 210, "bpm": 140, "key": "E Minor"},
                {"id": 11, "name": "Electric Storm", "duration": 195, "bpm": 145, "key": "A Minor"},
                {"id": 12, "name": "Power Chord", "duration": 180, "bpm": 135, "key": "D Minor"},
                {"id": 13, "name": "Rock Anthem", "duration": 240, "bpm": 130, "key": "G Minor"},
                {"id": 14, "name": "Guitar Hero", "duration": 220, "bpm": 138, "key": "C Minor"},
                {"id": 15, "name": "Metal Fusion", "duration": 200, "bpm": 142, "key": "F Minor"},
                {"id": 16, "name": "Drum Solo", "duration": 160, "bpm": 150, "key": "B Minor"},
                {"id": 17, "name": "Bass Drop", "duration": 185, "bpm": 136, "key": "E Minor"},
                {"id": 18, "name": "Amplified", "duration": 205, "bpm": 144, "key": "A Minor"}
            ],
            "Pop": [
                {"id": 19, "name": "Catchy Beat", "duration": 180, "bpm": 120, "key": "C Major"},
                {"id": 20, "name": "Dance Floor", "duration": 200, "bpm": 125, "key": "G Major"},
                {"id": 21, "name": "Radio Hit", "duration": 190, "bpm": 118, "key": "F Major"},
                {"id": 22, "name": "Upbeat Melody", "duration": 175, "bpm": 122, "key": "D Major"},
                {"id": 23, "name": "Feel Good", "duration": 185, "bpm": 115, "key": "A Major"},
                {"id": 24, "name": "Summer Vibes", "duration": 195, "bpm": 128, "key": "E Major"},
                {"id": 25, "name": "Chart Topper", "duration": 170, "bpm": 120, "key": "B♭ Major"},
                {"id": 26, "name": "Mainstream", "duration": 188, "bpm": 124, "key": "C Major"},
                {"id": 27, "name": "Pop Anthem", "duration": 205, "bpm": 116, "key": "G Major"}
            ],
            "Rap": [
                {"id": 28, "name": "Street Beats", "duration": 200, "bpm": 95, "key": "E Minor"},
                {"id": 29, "name": "Urban Flow", "duration": 180, "bpm": 88, "key": "A Minor"},
                {"id": 30, "name": "Hip Hop Classic", "duration": 220, "bpm": 92, "key": "D Minor"},
                {"id": 31, "name": "Freestyle", "duration": 160, "bpm": 100, "key": "G Minor"},
                {"id": 32, "name": "Boom Bap", "duration": 195, "bpm": 85, "key": "C Minor"},
                {"id": 33, "name": "Trap Beat", "duration": 175, "bpm": 105, "key": "F Minor"},
                {"id": 34, "name": "Conscious Rap", "duration": 240, "bpm": 90, "key": "B Minor"},
                {"id": 35, "name": "Underground", "duration": 210, "bpm": 87, "key": "E Minor"},
                {"id": 36, "name": "Lyrical Flow", "duration": 185, "bpm": 93, "key": "A Minor"}
            ],
            "R&B": [
                {"id": 37, "name": "Smooth Soul", "duration": 220, "bpm": 75, "key": "C Major"},
                {"id": 38, "name": "Velvet Voice", "duration": 240, "bpm": 70, "key": "G Major"},
                {"id": 39, "name": "Groove Master", "duration": 200, "bpm": 78, "key": "F Major"},
                {"id": 40, "name": "Soulful Nights", "duration": 260, "bpm": 68, "key": "D Major"},
                {"id": 41, "name": "Love Ballad", "duration": 210, "bpm": 72, "key": "A Major"},
                {"id": 42, "name": "Midnight Groove", "duration": 195, "bpm": 76, "key": "E Major"},
                {"id": 43, "name": "Neo Soul", "duration": 225, "bpm": 74, "key": "B♭ Major"},
                {"id": 44, "name": "Rhythm & Blues", "duration": 250, "bpm": 65, "key": "C Major"},
                {"id": 45, "name": "Smooth Operator", "duration": 180, "bpm": 80, "key": "G Major"}
            ],
        }

        written = 0
        for category, tracks in catalog.items():
            for t in tracks:
                song_id = str(t["id"]).strip()
                payload = {
                    "name": t.get("name"),
                    "duration": t.get("duration"),
                    "bpm": t.get("bpm"),
                    "key": t.get("key"),
                    "category": category,
                    "url": self._default_audio_url(category),
                }
                if self.put_song(song_id, payload):
                    written += 1
        return written

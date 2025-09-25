import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import os
import joblib
from datetime import datetime, timedelta
from db import DDB

# Class labels mapping (1-based indexing):
# 1->Classical, 2->Rock, 3->Pop, 4->Rap, 5->R&B
CLASS_LABELS = ["Classical", "Rock", "Pop", "Rap", "R&B"]

def class_value_to_label(val) -> str:
    """Map a model class value to a readable label using 1-based indexing.

    Rules:
    - If val is an int/str-int n in [1..len(CLASS_LABELS)], map to CLASS_LABELS[n-1].
    - If val is already a string matching one of CLASS_LABELS, return as-is.
    - Else, fallback to f"Class {val}".
    """
    try:
        n = int(val)
        if 1 <= n <= len(CLASS_LABELS):
            return CLASS_LABELS[n-1]
    except Exception:
        pass
    # try direct string match
    try:
        s = str(val)
        if s in CLASS_LABELS:
            return s
    except Exception:
        pass
    return f"Class {val}"


# -----------------------------
# Model loading (optional)
# -----------------------------
def load_model():
    """Load default pre-trained model if available (best_RF_with_time).

    The model file is expected to be placed at project root path
    as "best_RF_with_time" (a joblib artifact). If not found, we proceed
    without a model.
    """
    try:
        model_path = Path(__file__).parent / "best_Sub03_RF"
        if not model_path.exists() or not os.access(str(model_path), os.R_OK):
            return None
        model = joblib.load(str(model_path))
        return model
    except Exception:
        return None


# -----------------------------
# Cognitive score helpers
# -----------------------------
def calculate_engagement_score(row: pd.Series) -> float:
    """Engagement: Mean(Beta+Gamma) - Mean(Alpha+Theta) across electrodes."""
    beta_mean = (
        row.get('Beta_TP9_mean', 0) + row.get('Beta_AF7_mean', 0) +
        row.get('Beta_AF8_mean', 0) + row.get('Beta_TP10_mean', 0)
    ) / 4
    gamma_mean = (
        row.get('Gamma_TP9_mean', 0) + row.get('Gamma_AF7_mean', 0) +
        row.get('Gamma_AF8_mean', 0) + row.get('Gamma_TP10_mean', 0)
    ) / 4
    alpha_mean = (
        row.get('Alpha_TP9_mean', 0) + row.get('Alpha_AF7_mean', 0) +
        row.get('Alpha_AF8_mean', 0) + row.get('Alpha_TP10_mean', 0)
    ) / 4
    theta_mean = (
        row.get('Theta_TP9_mean', 0) + row.get('Theta_AF7_mean', 0) +
        row.get('Theta_AF8_mean', 0) + row.get('Theta_TP10_mean', 0)
    ) / 4
    high_freq = (beta_mean + gamma_mean) / 2
    low_freq = (alpha_mean + theta_mean) / 2
    return float(high_freq - low_freq)


def calculate_focus_score(row: pd.Series) -> float:
    """Focus: Theta/Beta ratio (lower is better focus)."""
    beta_mean = (
        row.get('Beta_TP9_mean', 0) + row.get('Beta_AF7_mean', 0) +
        row.get('Beta_AF8_mean', 0) + row.get('Beta_TP10_mean', 0)
    ) / 4
    theta_mean = (
        row.get('Theta_TP9_mean', 0) + row.get('Theta_AF7_mean', 0) +
        row.get('Theta_AF8_mean', 0) + row.get('Theta_TP10_mean', 0)
    ) / 4
    if beta_mean == 0:
        return float('inf')
    return float(theta_mean / beta_mean)


def calculate_relaxation_score(row: pd.Series) -> float:
    """Relaxation: Mean(Alpha+Theta) - Mean(Beta+Gamma) across electrodes."""
    alpha_mean = (
        row.get('Alpha_TP9_mean', 0) + row.get('Alpha_AF7_mean', 0) +
        row.get('Alpha_AF8_mean', 0) + row.get('Alpha_TP10_mean', 0)
    ) / 4
    theta_mean = (
        row.get('Theta_TP9_mean', 0) + row.get('Theta_AF7_mean', 0) +
        row.get('Theta_AF8_mean', 0) + row.get('Theta_TP10_mean', 0)
    ) / 4
    beta_mean = (
        row.get('Beta_TP9_mean', 0) + row.get('Beta_AF7_mean', 0) +
        row.get('Beta_AF8_mean', 0) + row.get('Beta_TP10_mean', 0)
    ) / 4
    gamma_mean = (
        row.get('Gamma_TP9_mean', 0) + row.get('Gamma_AF7_mean', 0) +
        row.get('Gamma_AF8_mean', 0) + row.get('Gamma_TP10_mean', 0)
    ) / 4
    calm_freq = (alpha_mean + theta_mean) / 2
    active_freq = (beta_mean + gamma_mean) / 2
    return float(calm_freq - active_freq)


def process_eeg_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute cognitive scores per row without any grouping/aggregation."""
    out = df.copy()

    # Compute row-wise (no groupby) aggregate bands if columns exist
    for band in ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']:
        band_cols = [c for c in out.columns if c.startswith(f"{band}_") and c.endswith('_mean')]
        if band_cols:
            out[band.lower()] = out[band_cols].mean(axis=1)

    # Cognitive scores per row
    out['engagement_score'] = out.apply(calculate_engagement_score, axis=1)
    out['focus_score'] = out.apply(calculate_focus_score, axis=1)
    out['relaxation_score'] = out.apply(calculate_relaxation_score, axis=1)

    # Normalize to 0-10 scale per-file (still row-specific, not grouped)
    for col in ['engagement_score', 'focus_score', 'relaxation_score']:
        min_v = out[col].min()
        max_v = out[col].max()
        if pd.isna(min_v) or pd.isna(max_v) or max_v == min_v:
            out[f'{col}_normalized'] = 5.0
        else:
            out[f'{col}_normalized'] = 10 * (out[col] - min_v) / (max_v - min_v)

    return out


# -----------------------------
# Session state init
# -----------------------------
def initialize_caregiver_session_state():
    if 'processed_eeg_data' not in st.session_state:
        st.session_state.processed_eeg_data = None
    if 'ml_model_results' not in st.session_state:
        model = load_model()
        st.session_state.ml_model_results = {
            'model': model,
            'loaded_from_file': bool(model),
            'accuracy': 0.0,
        }
    # Track selected patient for recommendations linkage
    if 'patient_id' not in st.session_state:
        st.session_state.patient_id = ""

# Firestore is the only persistence layer for recommendations


def run_predictions_on_uploaded_data():
    """Run model predictions on st.session_state.processed_eeg_data if possible.

    Adds columns to the dataframe:
    - predicted_class (from model.predict)
    - predicted_proba_max (if predict_proba available)
    - predicted_proba_top_index (index of class with max proba)
    """
    results = st.session_state.get('ml_model_results')
    df = st.session_state.get('processed_eeg_data')
    if not results or not results.get('model') or df is None or df.empty:
        st.warning("Model or data not available.")
        return

    # Build features directly from uploaded CSV: include ALL numeric columns
    # except the label and any columns our app created (engineered/normalized/prediction/timestamps).
    created_prefixes = (
        'engagement_score', 'focus_score', 'relaxation_score',
        'predicted_',
    )
    created_exact = {
        'delta', 'theta', 'alpha', 'beta', 'gamma',
        'melody_category', 'Melody #', 'timestamp'
    }
    def is_created(col: str) -> bool:
        if col in created_exact:
            return True
        if any(col.startswith(p) for p in created_prefixes):
            return True
        if col.endswith('_normalized'):
            return True
        return False

    used_cols = [
        c for c in df.columns
        if not is_created(c) and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not used_cols:
        st.error("No suitable numeric feature columns found for prediction.")
        return
    X = df[used_cols].values

    model = results['model']
    try:
        # Predict classes
        y_pred = model.predict(X)
        df_out = df.copy()
        df_out['predicted_class'] = y_pred
        # Map to human-readable labels using 1-based indexing via class_value_to_label
        try:
            if hasattr(model, 'classes_') and len(getattr(model, 'classes_')):
                classes = list(model.classes_)
                # Map predicted class values directly to labels based on their value (1-based expected)
                val_to_label = {cls_val: class_value_to_label(cls_val) for cls_val in classes}
                df_out['predicted_label'] = [val_to_label.get(val, class_value_to_label(val)) for val in y_pred]
            else:
                # Fallback: map predicted values directly assuming 1-based values
                df_out['predicted_label'] = [class_value_to_label(i) for i in y_pred]
        except Exception:
            pass

        # Predict probabilities if available
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X)
            max_proba = proba.max(axis=1)
            top_idx = proba.argmax(axis=1)  # positions in classes_
            df_out['predicted_proba_max'] = max_proba
            df_out['predicted_proba_top_index'] = top_idx
            # Also store the top label resolved by classes_ ordering
            try:
                if hasattr(model, 'classes_') and len(getattr(model, 'classes_')):
                    classes = list(model.classes_)
                    df_out['predicted_top_label'] = [class_value_to_label(classes[i]) for i in top_idx]
            except Exception:
                pass

        st.session_state.processed_eeg_data = df_out
        st.success("Predictions added to the dataset.")
        
        # Quick summary
        if 'predicted_class' in df_out.columns:
            st.subheader("Prediction Summary")
            st.write(df_out['predicted_class'].value_counts().rename_axis('class').to_frame('count'))

        # Save top category recommendations for the specified patient
        patient_id = (st.session_state.get('patient_id') or "").strip()
        if patient_id:
            # Prefer probability-weighted top labels if available, else use predicted_label counts
            if 'predicted_top_label' in df_out.columns and 'predicted_proba_max' in df_out.columns:
                agg = (
                    df_out.groupby('predicted_top_label')['predicted_proba_max']
                    .sum()
                    .sort_values(ascending=False)
                )
                total = float(agg.sum()) or 1.0
                ranked = [{
                    'category': str(cat),
                    'score': float(val / total)
                } for cat, val in agg.items()]
            elif 'predicted_label' in df_out.columns:
                vc = df_out['predicted_label'].value_counts(normalize=True)
                ranked = [{
                    'category': str(cat),
                    'score': float(score)
                } for cat, score in vc.items()]
            else:
                ranked = []

            if ranked:
                # Compute cognitive metric averages from processed data (0-10 scale)
                avg_eng = float(df_out['engagement_score_normalized'].mean()) if 'engagement_score_normalized' in df_out.columns else None
                # Focus is inverted so higher is better (10 - normalized theta/beta)
                avg_foc = float((10 - df_out['focus_score_normalized']).mean()) if 'focus_score_normalized' in df_out.columns else None
                avg_rel = float(df_out['relaxation_score_normalized'].mean()) if 'relaxation_score_normalized' in df_out.columns else None

                # Persist directly to Firestore only
                # Persist to Firestore via DDB (errors will surface)
                ddb = DDB()
                ok = ddb.put_recommendations(
                    patient_id,
                    categories=ranked,
                    cognitive_scores={
                        'engagement': round(avg_eng, 2) if avg_eng is not None else None,
                        'focus': round(avg_foc, 2) if avg_foc is not None else None,
                        'relaxation': round(avg_rel, 2) if avg_rel is not None else None,
                    }
                )
                if ok:
                    st.success(f"Saved caregiver playlist recommendations for '{patient_id}'.")
                else:
                    st.error("Failed to save recommendations.")
        else:
            st.info("Enter a Patient ID (email) in EEG Upload to save playlist recommendations.")
    except Exception as e:
        st.error(f"Error running predictions: {e}")


# -----------------------------
# Dashboards (non-patient)
# -----------------------------
def ml_model_dashboard():
    st.subheader("🤖 ML Model Performance")
    results = st.session_state.ml_model_results

    if results and results.get('loaded_from_file'):
        st.success("✅ Using Pre-trained Model: best_Sub03_RF")
        st.info("Upload EEG data to run per-row predictions and review cognitive scores.")
        # Allow running predictions if data exists
        df = st.session_state.get('processed_eeg_data')
        if df is not None and not df.empty:
            if st.button("Run Predictions on Uploaded EEG Data"):
                run_predictions_on_uploaded_data()
            # Show a compact prediction analytics pie (no tables)
            df = st.session_state.get('processed_eeg_data')
            try:
                if df is not None and 'predicted_proba_max' in df.columns:
                    last_row = df.iloc[-1]
                    prob = float(last_row.get('predicted_proba_max', 0.0))
                    label = None
                    # Prefer predicted_top_label if present
                    if 'predicted_top_label' in df.columns and isinstance(last_row.get('predicted_top_label'), str):
                        label = str(last_row['predicted_top_label'])
                    else:
                        # Map via model.classes_ and top index if available
                        if 'predicted_proba_top_index' in df.columns:
                            try:
                                top_idx = int(last_row['predicted_proba_top_index'])
                                if hasattr(results.get('model'), 'classes_') and len(getattr(results.get('model'), 'classes_')):
                                    classes = list(results.get('model').classes_)
                                    cls_val = classes[top_idx]
                                    label = class_value_to_label(cls_val)
                            except Exception:
                                pass
                    # Final fallback using predicted_label or class index
                    if not label:
                        if 'predicted_label' in df.columns and isinstance(last_row.get('predicted_label'), str):
                            label = str(last_row['predicted_label'])
                        else:
                            label = "Top Class"

                    # Color by strength
                    if prob >= 0.8:
                        color = "#2ecc71"  # green
                    elif prob >= 0.6:
                        color = "#27ae60"  # dark green
                    elif prob >= 0.4:
                        color = "#f39c12"  # orange
                    else:
                        color = "#e74c3c"  # red

                    achieved = max(0.0, min(1.0, prob))
                    remaining = 1.0 - achieved
                    pie_fig = go.Figure(data=[go.Pie(
                        labels=[f"{label}", "Remaining"],
                        values=[achieved, remaining],
                        hole=0.6,
                        marker=dict(colors=[color, "#E0E0E0"]),
                        textinfo='label+percent'
                    )])
                    pie_fig.update_layout(title=f"Top Class: {label} — {prob*100:.1f}%")
                    st.plotly_chart(pie_fig, use_container_width=True)
            except Exception:
                pass
    else:
        st.warning("No model found. Place 'best_Sub03_RF' (joblib) in project root to enable predictions.")


def cognitive_insights_dashboard(df: pd.DataFrame):
    st.subheader("🧠 Cognitive Scores Summary")

    if df is None or df.empty:
        st.info("No data loaded. Use 'EEG Data Upload' to add a CSV.")
        return

    # Compute summary stats (assuming single-patient file)
    avg_eng = float(df['engagement_score_normalized'].mean()) if 'engagement_score_normalized' in df.columns else None
    avg_foc_inv = float((10 - df['focus_score_normalized']).mean()) if 'focus_score_normalized' in df.columns else None
    avg_rel = float(df['relaxation_score_normalized'].mean()) if 'relaxation_score_normalized' in df.columns else None

    col1, col2, col3 = st.columns(3)
    with col1:
        if avg_eng is not None:
            st.metric("Avg Engagement", f"{avg_eng:.1f}/10")
            # Engagement pie chart (Achieved vs Remaining out of 10)
            achieved = max(0.0, min(10.0, avg_eng))
            remaining = max(0.0, 10.0 - achieved)
            pie_fig = go.Figure(data=[go.Pie(
                labels=["Achieved", "Remaining"],
                values=[achieved, remaining],
                hole=0.5,
                marker=dict(colors=["#FF6B6B", "#E0E0E0"]),
                textinfo='label+percent'
            )])
            pie_fig.update_layout(title=f"Engagement Achieved: {achieved:.1f}/10")
            st.plotly_chart(pie_fig, use_container_width=True)
    with col2:
        if avg_foc_inv is not None:
            st.metric("Avg Focus", f"{avg_foc_inv:.1f}/10")
    with col3:
        if avg_rel is not None:
            st.metric("Avg Relaxation", f"{avg_rel:.1f}/10")


def caregiver_dashboard():
    """Main caregiver dashboard (no patient-specific analysis)."""
    initialize_caregiver_session_state()

    user_info = st.session_state.get('user_info', {'name': 'Caregiver'})
    st.title("👩‍⚕️ Caregiver ML Analytics Dashboard")
    st.markdown(f"Welcome, **{user_info.get('name', 'Caregiver')}**. Upload EEG CSV and review per-row insights.")

    # Sidebar navigation
    with st.sidebar:
        st.markdown("### 🧠 ML Analytics")
        page = st.selectbox(
            "Select Analysis",
            ["ML Model Performance", "Cognitive Insights", "EEG Data Upload"],
        )

    # Main pages
    if page == "ML Model Performance":
        ml_model_dashboard()

    elif page == "Cognitive Insights":
        cognitive_insights_dashboard(st.session_state.processed_eeg_data)

    elif page == "EEG Data Upload":
        st.subheader("📤 Upload EEG CSV (Generic)")
        # Capture patient identifier to link recommendations (use patient's email for best results)
        st.session_state.patient_id = st.text_input(
            "Patient ID (use patient's email to link to General User)",
            value=st.session_state.get('patient_id', ""),
            placeholder="name@example.com",
        )

        uploaded_file = st.file_uploader("Choose EEG CSV file", type="csv")
        if uploaded_file is not None:
            try:
                df_new = pd.read_csv(uploaded_file)

                # Coerce timestamp if provided
                if 'timestamp' in df_new.columns:
                    df_new['timestamp'] = pd.to_datetime(df_new['timestamp'], errors='coerce')

                processed = process_eeg_scores(df_new)
                st.session_state.processed_eeg_data = processed
                st.success(f"Loaded {len(processed)} rows. Switch to 'Cognitive Insights' to explore.")
            except Exception as e:
                st.error(f"Error processing file: {e}")



def caregiver_dashboard_legacy():
    """[REMOVED] Legacy patient-specific dashboard code has been removed."""
    st.error("This function is deprecated and not available.")

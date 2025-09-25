import streamlit as st
import pandas as pd
from pathlib import Path
import os
import joblib
from db import DDB

# Class labels mapping (1-based indexing):
# 1->Classical, 2->Rock, 3->Pop, 4->Rap, 5->R&B
CLASS_LABELS = ["Classical", "Rock", "Pop", "Rap", "R&B"]
ELECTRODES = ['TP9', 'AF7', 'AF8', 'TP10']
BANDS = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']

def class_value_to_label(val) -> str:
    """Map a model class value to a readable label using 1-based indexing."""
    try:
        n = int(val)
        if 1 <= n <= len(CLASS_LABELS):
            return CLASS_LABELS[n-1]
    except (ValueError, TypeError):
        pass
    return str(val) if str(val) in CLASS_LABELS else f"Class {val}"

def calculate_band_means(row: pd.Series, band: str) -> float:
    """Calculate mean of a frequency band across all electrodes."""
    band_means = [row.get(f"{band}_{elec}_mean", 0) for elec in ELECTRODES]
    return sum(band_means) / len(ELECTRODES)

def load_model():
    """Load default pre-trained model if available."""
    try:
        model_path = Path(__file__).parent / "best_Sub03_RF"
        if model_path.exists() and os.access(str(model_path), os.R_OK):
            return joblib.load(str(model_path))
    except Exception:
        pass
    return None

def calculate_engagement_score(row: pd.Series) -> float:
    """Calculate engagement score from beta and gamma vs alpha and theta bands."""
    beta_mean = calculate_band_means(row, 'Beta')
    gamma_mean = calculate_band_means(row, 'Gamma')
    alpha_mean = calculate_band_means(row, 'Alpha')
    theta_mean = calculate_band_means(row, 'Theta')
    return (beta_mean + gamma_mean) / 2 - (alpha_mean + theta_mean) / 2

def calculate_focus_score(row: pd.Series) -> float:
    """Calculate focus score as Theta/Beta ratio."""
    beta_mean = calculate_band_means(row, 'Beta')
    theta_mean = calculate_band_means(row, 'Theta')
    return float('inf') if beta_mean == 0 else theta_mean / beta_mean

def calculate_relaxation_score(row: pd.Series) -> float:
    """Calculate relaxation score from alpha and theta vs beta and gamma bands."""
    return -calculate_engagement_score(row)  # Engagement and relaxation are inversely related

def process_eeg_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute cognitive scores per row without any grouping/aggregation."""
    out = df.copy()
    
    # Add mean band values
    for band in BANDS:
        out[band.lower()] = out.apply(lambda r: calculate_band_means(r, band), axis=1)
    
    # Calculate cognitive scores
    score_functions = {
        'engagement_score': calculate_engagement_score,
        'focus_score': calculate_focus_score,
        'relaxation_score': calculate_relaxation_score
    }
    
    for score_name, score_func in score_functions.items():
        out[score_name] = out.apply(score_func, axis=1)
        # Normalize to 0-10 scale
        min_v = out[score_name].min()
        max_v = out[score_name].max()
        norm_col = f'{score_name}_normalized'
        out[norm_col] = 5.0 if (pd.isna(min_v) or pd.isna(max_v) or max_v == min_v) else \
                       10 * (out[score_name] - min_v) / (max_v - min_v)
    
    return out

def initialize_caregiver_session_state():
    """Initialize session state variables."""
    defaults = {
        'processed_eeg_data': None,
        'ml_model_results': {'model': load_model(), 'loaded_from_file': False, 'accuracy': 0.0},
        'patient_id': ""
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def run_predictions_on_uploaded_data():
    """Run model predictions on the uploaded EEG data."""
    results = st.session_state.get('ml_model_results', {})
    df = st.session_state.get('processed_eeg_data')
    
    if not results.get('model') or df is None or df.empty:
        st.warning("Model or data not available.")
        return

    # Get feature columns
    exclude_prefixes = ('engagement_score', 'focus_score', 'relaxation_score', 'predicted_')
    exclude_exact = {'delta', 'theta', 'alpha', 'beta', 'gamma', 'melody_category', 'Melody #', 'timestamp'}
    
    used_cols = [
        c for c in df.columns
        if not (any(c.startswith(p) for p in exclude_prefixes) or 
                c in exclude_exact or 
                c.endswith('_normalized') or
                not pd.api.types.is_numeric_dtype(df[c]))
    ]
    
    if not used_cols:
        st.error("No suitable numeric feature columns found for prediction.")
        return

    try:
        X = df[used_cols].values
        model = results['model']
        df_out = df.copy()
        
        # Make predictions
        y_pred = model.predict(X)
        df_out['predicted_class'] = y_pred
        
        # Map to human-readable labels
        if hasattr(model, 'classes_'):
            class_mapping = {cls: class_value_to_label(cls) for cls in model.classes_}
            df_out['predicted_label'] = [class_mapping.get(c, str(c)) for c in y_pred]
        
        # Get probabilities if available
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X)
            df_out['predicted_proba_max'] = proba.max(axis=1)
            df_out['predicted_proba_top_index'] = proba.argmax(axis=1)
            
            if hasattr(model, 'classes_'):
                df_out['predicted_top_label'] = [class_value_to_label(model.classes_[i]) 
                                              for i in df_out['predicted_proba_top_index']]
        
        st.session_state.processed_eeg_data = df_out
        st.success("Predictions added to the dataset.")
        
        # Save recommendations if patient ID is provided
        patient_id = (st.session_state.get('patient_id') or "").strip()
        if patient_id and 'predicted_label' in df_out.columns:
            save_recommendations(patient_id, df_out)
            
    except Exception as e:
        st.error(f"Error running predictions: {e}")

def save_recommendations(patient_id: str, df: pd.DataFrame):
    """Save recommendations for a patient to the database."""
    if 'predicted_top_label' in df.columns and 'predicted_proba_max' in df.columns:
        agg = df.groupby('predicted_top_label')['predicted_proba_max'].sum()
        ranked = [{'category': str(cat), 'score': float(val/agg.sum())} 
                 for cat, val in agg.items()]
    else:
        vc = df['predicted_label'].value_counts(normalize=True)
        ranked = [{'category': str(cat), 'score': float(score)} 
                 for cat, score in vc.items()]
    
    if ranked:
        cognitive_scores = {
            'engagement': round(float(df['engagement_score_normalized'].mean()), 2) 
                         if 'engagement_score_normalized' in df.columns else None,
            'focus': round(float((10 - df['focus_score_normalized']).mean()), 2) 
                     if 'focus_score_normalized' in df.columns else None,
            'relaxation': round(float(df['relaxation_score_normalized'].mean()), 2) 
                         if 'relaxation_score_normalized' in df.columns else None
        }
        
        ddb = DDB()
        if ddb.put_recommendations(patient_id, categories=ranked, cognitive_scores=cognitive_scores):
            st.success(f"Saved caregiver playlist recommendations for '{patient_id}'.")
        else:
            st.error("Failed to save recommendations.")

def ml_model_dashboard():
    st.subheader(" ML Model Performance")
    results = st.session_state.ml_model_results

    if results and results.get('loaded_from_file'):
        st.success(" Using Pre-trained Model: best_Sub03_RF")
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
    st.subheader(" Cognitive Scores Summary")

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
    st.title(" Caregiver ML Analytics Dashboard")
    st.markdown(f"Welcome, **{user_info.get('name', 'Caregiver')}**. Upload EEG CSV and review per-row insights.")

    # Sidebar navigation
    with st.sidebar:
        st.markdown("### ML Analytics")
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
        st.subheader(" Upload EEG CSV (Generic)")
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

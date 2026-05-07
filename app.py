import os
from datetime import datetime, timezone

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
from supabase import create_client

load_dotenv()

st.set_page_config(page_title="Allergy Predictor Pro", page_icon="NA", layout="wide")


@st.cache_resource
def load_data():
    return joblib.load("allergy_predictor_v1.pkl")


@st.cache_resource
def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        return None

    return create_client(url, key)


def encode_input(user_input, feature_columns):
    input_df = pd.DataFrame([user_input])
    return pd.get_dummies(input_df).reindex(columns=feature_columns, fill_value=0)


def calculate_risks(models, encoded_input):
    risks = {}
    for name, model in models.items():
        probability = model.predict_proba(encoded_input)[0][1]
        risks[name] = round(probability * 100, 1)
    return risks


def build_pdf_report(birth_year, gender, race, has_asthma, has_eczema, risk_map):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="Allergy Risk Assessment Report", ln=True, align="C")
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Patient Birth Year: {birth_year}", ln=True)
    pdf.cell(200, 10, txt=f"Gender: {gender}", ln=True)
    pdf.cell(200, 10, txt=f"Race: {race}", ln=True)
    pdf.cell(200, 10, txt=f"Asthma history: {'Yes' if has_asthma else 'No'}", ln=True)
    pdf.cell(200, 10, txt=f"Eczema history: {'Yes' if has_eczema else 'No'}", ln=True)
    pdf.ln(5)

    for allergen, risk in risk_map.items():
        pdf.cell(200, 10, txt=f"- {allergen.upper()}: {risk}%", ln=True)

    return pdf.output(dest="S").encode("latin-1")


def store_submission(client, payload):
    return client.table("allergy_assessments").insert(payload).execute()


def fetch_recent_submissions(client, limit=5):
    return client.table("allergy_assessments").select("created_at,birth_year,gender_factor,race_factor,has_asthma,has_eczema,predicted_risks").order("created_at", desc=True).limit(limit).execute()


data = load_data()
models = data["models"]
feature_columns = data["X_columns"]
supabase_client = get_supabase_client()

st.title("Food Allergy Risk Predictor")
st.markdown(
    "This app uses machine learning to estimate the likelihood of 15 food allergies from demographic data and atopic history."
)

st.sidebar.header("Patient data")
with st.sidebar.form("patient_form"):
    birth_year = st.number_input("Birth year", 1980, 2026, 2018)
    gender = st.selectbox("Gender", ["S0 - Male", "S1 - Female"])
    race = st.selectbox("Race", ["R0 - White", "R1 - Black", "R2 - Asian", "R3 - Other"])
    has_asthma = st.checkbox("Asthma history")
    has_eczema = st.checkbox("Eczema history")
    submitted = st.form_submit_button("Calculate and save to Supabase")

if submitted:
    user_input = {
        "BIRTH_YEAR": birth_year,
        "GENDER_FACTOR": gender,
        "RACE_FACTOR": race,
        "ETHNICITY_FACTOR": "E0 - Non-Hispanic",
        "HAS_ASTHMA": int(has_asthma),
        "HAS_ECZEMA": int(has_eczema),
    }

    encoded_input = encode_input(user_input, feature_columns)
    risk_map = calculate_risks(models, encoded_input)

    st.subheader("Predicted allergy risk")
    all_names = list(models.keys())

    for index in range(0, len(all_names), 3):
        columns = st.columns(3)
        for offset in range(3):
            if index + offset < len(all_names):
                allergen = all_names[index + offset]
                risk = risk_map[allergen]
                status = "High" if risk > 40 else "Medium" if risk > 15 else "Low"

                with columns[offset]:
                    st.metric(label=allergen.upper(), value=f"{risk}%", delta=status, delta_color="inverse")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Key factor analysis")
        example_model = models["peanut"].steps[1][1]
        importance_df = pd.DataFrame(
            {
                "Feature": feature_columns,
                "Impact": example_model.coef_[0],
            }
        ).sort_values("Impact")

        fig, ax = plt.subplots()
        colors = ["#ff9999" if value > 0 else "#66b3ff" for value in importance_df["Impact"]]
        ax.barh(importance_df["Feature"], importance_df["Impact"], color=colors)
        st.pyplot(fig)
        st.caption("Red increases risk, blue decreases it.")

    with col_right:
        st.subheader("PDF report")
        st.write("Generate a document with the assessment results.")
        pdf_output = build_pdf_report(birth_year, gender, race, has_asthma, has_eczema, risk_map)
        st.download_button(
            label="Download PDF report",
            data=pdf_output,
            file_name="allergy_report.pdf",
            mime="application/pdf",
        )

    submission_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "birth_year": int(birth_year),
        "gender_factor": gender,
        "race_factor": race,
        "ethnicity_factor": "E0 - Non-Hispanic",
        "has_asthma": bool(has_asthma),
        "has_eczema": bool(has_eczema),
        "raw_input": user_input,
        "predicted_risks": risk_map,
        "model_version": "allergy_predictor_v1",
    }

    if supabase_client is None:
        st.warning(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY to save submissions to the database."
        )
    else:
        try:
            result = store_submission(supabase_client, submission_payload)
            st.success("Saved to Supabase.")
            if result.data:
                st.json(result.data[0])
        except Exception as exc:
            st.error(f"Could not save submission to Supabase: {exc}")

        try:
            recent_result = fetch_recent_submissions(supabase_client)
            if recent_result.data:
                st.subheader("Recent saved assessments")
                st.dataframe(pd.DataFrame(recent_result.data), use_container_width=True)
        except Exception as exc:
            st.warning(f"Saved submission, but could not load recent records: {exc}")

    st.info("This system is for demonstration only. It is not a medical diagnosis tool.")
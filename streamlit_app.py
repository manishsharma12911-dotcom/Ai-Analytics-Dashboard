import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="AI Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 AI Analytics Dashboard")
st.write("Application deployed successfully!")

st.info(
    "Excel upload and AI-powered dashboard features "
    "will be added next."
)
uploaded_file = st.file_uploader(
    "📁 Upload your Excel file",
    type=["xlsx", "xls"]
)
df = pd.read_excel(uploaded_file)

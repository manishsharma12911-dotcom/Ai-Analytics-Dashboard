import streamlit as st
import pandas as pd
from io import BytesIO

st.title("📊 AI Analytics Dashboard")

uploaded_file = st.file_uploader(
    "📁 Upload your Excel file",
    type=["xlsx", "xls"]
)

if uploaded_file is not None:
    try:
        # Read uploaded file into memory
        file_bytes = uploaded_file.getvalue()
        excel_file = BytesIO(file_bytes)

        # Use openpyxl for .xlsx files
        if uploaded_file.name.lower().endswith(".xlsx"):
            df = pd.read_excel(excel_file, engine="openpyxl")
        else:
            # .xls requires xlrd
            df = pd.read_excel(excel_file, engine="xlrd")

        st.success(f"Successfully loaded: {uploaded_file.name}")

        st.subheader("📋 Data Preview")
        st.dataframe(df.head(10), use_container_width=True)

        st.write("Rows:", df.shape[0])
        st.write("Columns:", df.shape[1])

    except Exception as e:
        st.error(f"Unable to read the Excel file: {e}")

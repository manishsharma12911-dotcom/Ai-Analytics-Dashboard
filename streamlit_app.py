import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="AI Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------
# CUSTOM HELPERS
# ---------------------------------------------------------
def detect_excel_engine(filename: str) -> str:
    """Return the correct pandas Excel engine."""
    if filename.lower().endswith(".xlsx"):
        return "openpyxl"
    return "xlrd"


def read_uploaded_excel(uploaded_file):
    """Read an uploaded Excel file into a DataFrame."""
    file_bytes = uploaded_file.getvalue()
    buffer = io.BytesIO(file_bytes)
    engine = detect_excel_engine(uploaded_file.name)

    return pd.read_excel(buffer, engine=engine)


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names while preserving readability."""
    df = df.copy()

    cleaned = []
    for col in df.columns:
        col = str(col).strip()
        col = re.sub(r"\s+", " ", col)
        cleaned.append(col)

    df.columns = cleaned
    return df


def detect_date_columns(df: pd.DataFrame):
    """Detect columns that are likely to contain dates."""
    date_columns = []

    for col in df.columns:
        series = df[col]

        if pd.api.types.is_datetime64_any_dtype(series):
            date_columns.append(col)
            continue

        # Don't try to parse obviously numeric columns as dates
        if pd.api.types.is_numeric_dtype(series):
            continue

        parsed = pd.to_datetime(series, errors="coerce")
        valid_ratio = parsed.notna().mean()

        if valid_ratio >= 0.75:
            date_columns.append(col)

    return date_columns


def detect_id_columns(df: pd.DataFrame):
    """Detect likely identifier columns."""
    id_columns = []

    for col in df.columns:
        name = str(col).lower()

        if (
            "id" in name
            or "code" in name
            or "number" in name
            or "no." in name
            or "number" in name
        ):
            id_columns.append(col)

    return id_columns


def choose_primary_measure(df: pd.DataFrame):
    """
    Find the most useful numeric business metric.
    Preference is given to common business metric names.
    """
    numeric_columns = df.select_dtypes(include=np.number).columns.tolist()

    if not numeric_columns:
        return None

    preferred_keywords = [
        "revenue",
        "sales",
        "amount",
        "premium",
        "claim",
        "profit",
        "income",
        "cost",
        "price",
        "value",
        "expense",
        "salary",
        "balance",
        "quantity",
        "units",
    ]

    scored_columns = []

    for col in numeric_columns:
        name = str(col).lower()

        score = 0

        for keyword in preferred_keywords:
            if keyword in name:
                score += 10

        # Avoid selecting ID-type numeric columns
        if any(keyword in name for keyword in ["id", "code", "zip", "postal"]):
            score -= 20

        scored_columns.append((score, col))

    scored_columns.sort(reverse=True)

    return scored_columns[0][1]


def choose_category_columns(df: pd.DataFrame, id_columns):
    """Find useful categorical columns for charts."""
    categorical_columns = df.select_dtypes(
        include=["object", "category", "bool"]
    ).columns.tolist()

    useful = []

    for col in categorical_columns:
        unique_count = df[col].nunique(dropna=True)

        # Avoid massive/high-cardinality dimensions
        if 2 <= unique_count <= 30:
            if col not in id_columns:
                useful.append(col)

    return useful


def format_number(value):
    """Readable KPI number formatting."""
    if pd.isna(value):
        return "N/A"

    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"{value / 1_000:.2f}K"

    return f"{value:,.2f}"


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("📊 AI Analytics Dashboard")
st.caption(
    "Upload an Excel file and automatically generate KPIs, charts and insights."
)


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
with st.sidebar:
    st.header("📁 Data Upload")

    uploaded_file = st.file_uploader(
        "Upload your Excel file",
        type=["xlsx", "xls"],
        help="Supported formats: .xlsx and .xls",
    )


# ---------------------------------------------------------
# EMPTY STATE
# ---------------------------------------------------------
if uploaded_file is None:
    st.info("👈 Upload an Excel file from the sidebar to generate your dashboard.")

    st.markdown(
        """
        ### What this dashboard does

        **1. Upload Excel**
        
        Upload your business dataset.

        **2. Automatic analysis**
        
        The app detects numeric, categorical, ID and date columns.

        **3. KPI generation**
        
        Important metrics are automatically calculated.

        **4. Dynamic charts**
        
        Charts are generated according to your dataset.
        """
    )

    st.stop()


# ---------------------------------------------------------
# READ DATA
# ---------------------------------------------------------
try:
    with st.spinner("Reading your Excel file..."):
        df = read_uploaded_excel(uploaded_file)
        df = clean_column_names(df)

except Exception as e:
    st.error(f"Unable to read the Excel file: {e}")
    st.stop()


if df.empty:
    st.warning("The uploaded Excel sheet is empty.")
    st.stop()


# ---------------------------------------------------------
# DATA PREPARATION
# ---------------------------------------------------------
date_columns = detect_date_columns(df)
id_columns = detect_id_columns(df)
numeric_columns = df.select_dtypes(include=np.number).columns.tolist()
category_columns = choose_category_columns(df, id_columns)

primary_measure = choose_primary_measure(df)


# Convert detected date columns
for col in date_columns:
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        df[col] = pd.to_datetime(df[col], errors="coerce")


# ---------------------------------------------------------
# SUCCESS MESSAGE
# ---------------------------------------------------------
st.success(
    f"✅ {uploaded_file.name} loaded successfully — "
    f"{len(df):,} rows × {len(df.columns):,} columns"
)


# ---------------------------------------------------------
# DATA PROFILE
# ---------------------------------------------------------
with st.expander("🔍 Dataset Profile"):
    profile_col1, profile_col2, profile_col3, profile_col4 = st.columns(4)

    profile_col1.metric("Rows", f"{len(df):,}")
    profile_col2.metric("Columns", f"{len(df.columns):,}")
    profile_col3.metric("Numeric Columns", len(numeric_columns))
    profile_col4.metric("Date Columns", len(date_columns))

    st.write("**Detected numeric columns:**")
    st.write(", ".join(map(str, numeric_columns)) or "None")

    st.write("**Detected categorical columns:**")
    st.write(", ".join(map(str, category_columns)) or "None")

    st.write("**Detected date columns:**")
    st.write(", ".join(map(str, date_columns)) or "None")


# ---------------------------------------------------------
# KPI SECTION
# ---------------------------------------------------------
st.subheader("📌 Key Performance Indicators")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)


# KPI 1 - Total Records
kpi1.metric(
    "Total Records",
    f"{len(df):,}"
)


# KPI 2 - Unique Customers / IDs
if id_columns:
    id_col = id_columns[0]
    unique_count = df[id_col].nunique()

    kpi2.metric(
        f"Unique {id_col}",
        f"{unique_count:,}"
    )
else:
    kpi2.metric(
        "Unique Values",
        "—"
    )


# KPI 3 - Total Primary Measure
if primary_measure:
    total_measure = df[primary_measure].sum()

    kpi3.metric(
        f"Total {primary_measure}",
        format_number(total_measure)
    )
else:
    kpi3.metric(
        "Total Measure",
        "—"
    )


# KPI 4 - Average Primary Measure
if primary_measure:
    avg_measure = df[primary_measure].mean()

    kpi4.metric(
        f"Average {primary_measure}",
        format_number(avg_measure)
    )
else:
    kpi4.metric(
        "Average Measure",
        "—"
    )


# ---------------------------------------------------------
# DASHBOARD CONTROLS
# ---------------------------------------------------------
st.subheader("🎛️ Dashboard Controls")

control1, control2 = st.columns(2)

with control1:
    if numeric_columns:
        selected_measure = st.selectbox(
            "Select metric",
            numeric_columns,
            index=(
                numeric_columns.index(primary_measure)
                if primary_measure in numeric_columns
                else 0
            ),
        )
    else:
        selected_measure = None

with control2:
    if category_columns:
        selected_category = st.selectbox(
            "Select category",
            category_columns,
        )
    else:
        selected_category = None


# ---------------------------------------------------------
# CHART 1 - CATEGORY ANALYSIS
# ---------------------------------------------------------
if selected_category and selected_measure:

    st.subheader(
        f"📊 {selected_measure} by {selected_category}"
    )

    grouped_data = (
        df.groupby(selected_category, dropna=False)[selected_measure]
        .sum()
        .reset_index()
        .sort_values(selected_measure, ascending=False)
        .head(15)
    )

    fig_bar = px.bar(
        grouped_data,
        x=selected_category,
        y=selected_measure,
        text_auto=".2s",
        title=f"{selected_measure} by {selected_category}",
    )

    fig_bar.update_layout(
        xaxis_title=selected_category,
        yaxis_title=selected_measure,
        height=450,
    )

    st.plotly_chart(
        fig_bar,
        use_container_width=True,
    )


# ---------------------------------------------------------
# CHART 2 - TIME TREND
# ---------------------------------------------------------
if date_columns and selected_measure:

    trend_date = date_columns[0]

    trend_data = (
        df.dropna(subset=[trend_date])
        .groupby(trend_date)[selected_measure]
        .sum()
        .reset_index()
        .sort_values(trend_date)
    )

    st.subheader(
        f"📈 {selected_measure} Trend"
    )

    fig_line = px.line(
        trend_data,
        x=trend_date,
        y=selected_measure,
        markers=True,
        title=f"{selected_measure} Over Time",
    )

    fig_line.update_layout(
        xaxis_title=trend_date,
        yaxis_title=selected_measure,
        height=450,
    )

    st.plotly_chart(
        fig_line,
        use_container_width=True,
    )


# ---------------------------------------------------------
# CHART 3 - DISTRIBUTION
# ---------------------------------------------------------
if selected_measure:

    st.subheader(
        f"📉 Distribution of {selected_measure}"
    )

    fig_hist = px.histogram(
        df,
        x=selected_measure,
        nbins=30,
        title=f"{selected_measure} Distribution",
    )

    fig_hist.update_layout(
        height=400,
        xaxis_title=selected_measure,
        yaxis_title="Count",
    )

    st.plotly_chart(
        fig_hist,
        use_container_width=True,
    )


# ---------------------------------------------------------
# TOP / BOTTOM ANALYSIS
# ---------------------------------------------------------
if selected_category and selected_measure:

    st.subheader("🏆 Top 10")

    ranking = (
        df.groupby(selected_category, dropna=False)[selected_measure]
        .sum()
        .reset_index()
        .sort_values(selected_measure, ascending=False)
        .head(10)
    )

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# DATA PREVIEW
# ---------------------------------------------------------
st.subheader("📋 Data Preview")

st.dataframe(
    df.head(100),
    use_container_width=True,
    height=400,
)


# ---------------------------------------------------------
# BASIC DATA QUALITY
# ---------------------------------------------------------
st.subheader("🧹 Data Quality")

missing_values = (
    df.isna()
    .sum()
    .reset_index()
)

missing_values.columns = ["Column", "Missing Values"]

missing_values["Missing %"] = (
    missing_values["Missing Values"] / len(df) * 100
).round(2)

missing_values = missing_values.sort_values(
    "Missing Values",
    ascending=False,
)

st.dataframe(
    missing_values,
    use_container_width=True,
    hide_index=True,
)

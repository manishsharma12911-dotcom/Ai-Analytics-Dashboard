"""
AI Analytics Dashboard
-----------------------
A modern, dynamic Streamlit app that:
  • Auto-detects column types (numeric, categorical, date, ID)
  • Generates smart KPIs and charts
  • Lets users filter data interactively from the sidebar
  • Includes a natural-language "Ask Your Data" Q&A box that lets
    users reshape the dashboard by typing plain-English requests
    (e.g. "show revenue by region", "top 5 products", "trend of sales")

Run with:  streamlit run app.py
"""

import io
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ===========================================================
# PAGE CONFIG & GLOBAL STYLE
# ===========================================================
st.set_page_config(
    page_title="AI Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY = "#6C5CE7"
ACCENT = "#00CEC9"
DARK = "#2D3436"
BG_CARD = "#FFFFFF"

CUSTOM_CSS = f"""
<style>
    .main {{ background-color: #F5F6FA; }}

    /* Header */
    .app-header {{
        padding: 1.6rem 2rem;
        border-radius: 18px;
        background: linear-gradient(120deg, {PRIMARY} 0%, {ACCENT} 100%);
        color: white;
        margin-bottom: 1.4rem;
        box-shadow: 0 8px 24px rgba(108,92,231,0.25);
    }}
    .app-header h1 {{ margin: 0; font-size: 2rem; font-weight: 800; }}
    .app-header p {{ margin: 0.3rem 0 0 0; opacity: 0.92; font-size: 0.95rem; }}

    /* KPI Cards */
    .kpi-card {{
        background: {BG_CARD};
        border-radius: 16px;
        padding: 1.1rem 1.3rem;
        box-shadow: 0 4px 14px rgba(45,52,54,0.08);
        border-left: 5px solid {PRIMARY};
        transition: transform 0.15s ease;
    }}
    .kpi-card:hover {{ transform: translateY(-3px); }}
    .kpi-label {{
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #636E72;
        font-weight: 600;
    }}
    .kpi-value {{
        font-size: 1.7rem;
        font-weight: 800;
        color: {DARK};
        margin-top: 0.15rem;
    }}
    .kpi-delta {{ font-size: 0.82rem; font-weight: 600; margin-top: 0.2rem; }}

    /* Section titles */
    .section-title {{
        font-size: 1.15rem;
        font-weight: 700;
        color: {DARK};
        margin: 0.6rem 0 0.4rem 0;
        border-left: 4px solid {ACCENT};
        padding-left: 0.6rem;
    }}

    /* Chat / Q&A bubble */
    .qa-answer {{
        background: #F0EFFF;
        border-left: 4px solid {PRIMARY};
        border-radius: 10px;
        padding: 0.8rem 1rem;
        font-size: 0.92rem;
        margin-bottom: 0.6rem;
        color: {DARK} !important;
    }}
    .qa-answer, .qa-answer * {{ color: {DARK} !important; }}
    .qa-answer b {{ color: {PRIMARY} !important; }}

    div[data-testid="stMetricValue"] {{ font-weight: 700; }}
    .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_white"
COLOR_SEQUENCE = px.colors.qualitative.Bold


# ===========================================================
# DATA HELPERS
# ===========================================================
def detect_excel_engine(filename: str) -> str:
    return "openpyxl" if filename.lower().endswith(".xlsx") else "xlrd"


@st.cache_data(show_spinner=False)
def read_uploaded_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    buffer = io.BytesIO(file_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buffer)
    engine = detect_excel_engine(filename)
    return pd.read_excel(buffer, engine=engine)


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c).strip()) for c in df.columns]
    return df


def detect_date_columns(df: pd.DataFrame):
    date_cols = []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            date_cols.append(col)
            continue
        if pd.api.types.is_numeric_dtype(series):
            continue
        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().mean() >= 0.75:
            date_cols.append(col)
    return date_cols


def detect_id_columns(df: pd.DataFrame):
    keywords = ["id", "code", "number", "no."]
    return [c for c in df.columns if any(k in str(c).lower() for k in keywords)]


def choose_primary_measure(df: pd.DataFrame):
    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
    if not numeric_cols:
        return None
    preferred = [
        "revenue", "sales", "amount", "premium", "claim", "profit", "income",
        "cost", "price", "value", "expense", "salary", "balance", "quantity", "units",
    ]
    scored = []
    for col in numeric_cols:
        name = str(col).lower()
        score = sum(10 for k in preferred if k in name)
        if any(k in name for k in ["id", "code", "zip", "postal"]):
            score -= 20
        scored.append((score, col))
    scored.sort(reverse=True)
    return scored[0][1]


def choose_category_columns(df: pd.DataFrame, id_columns):
    cat_cols = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
    return [c for c in cat_cols if c not in id_columns and 2 <= df[c].nunique(dropna=True) <= 30]


def format_number(value):
    if pd.isna(value):
        return "N/A"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.2f}K"
    return f"{sign}{value:,.2f}"


def kpi_card(label, value, delta=None, delta_positive=True):
    delta_html = ""
    if delta is not None:
        color = "#00B894" if delta_positive else "#D63031"
        arrow = "▲" if delta_positive else "▼"
        delta_html = f'<div class="kpi-delta" style="color:{color}">{arrow} {delta}</div>'
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================
# NATURAL-LANGUAGE QUERY ENGINE (rule-based, no external API)
# ===========================================================
STOPWORDS = {
    "show", "plot", "chart", "graph", "of", "by", "the", "a", "an", "for",
    "in", "on", "total", "sum", "average", "avg", "mean", "top", "trend",
    "over", "time", "distribution", "compare", "and", "vs", "versus", "me",
    "please", "give", "what", "is", "are", "count", "min", "max", "minimum",
    "maximum", "region", "category", "group", "wise", "breakdown",
}


def tokenize(text):
    return re.findall(r"[a-zA-Z0-9%]+", text.lower())


def find_best_column_match(query_tokens, candidates):
    """Fuzzy-match query words against real column names (word-overlap based)."""
    best_col, best_score = None, 0
    for col in candidates:
        col_tokens = set(tokenize(str(col)))
        overlap = sum(1 for t in query_tokens if t in col_tokens or any(t in ct or ct in t for ct in col_tokens))
        if overlap > best_score:
            best_score, best_col = overlap, col
    return best_col if best_score > 0 else None


def find_value_filter(query_tokens, df, category_cols):
    """
    Look for an actual data VALUE mentioned in the query (e.g. 'south' in a
    Region column with value 'South') and return (column, value) to filter on.
    """
    for col in category_cols:
        values = df[col].dropna().unique().tolist()
        for val in values:
            val_tokens = set(tokenize(str(val)))
            if val_tokens and val_tokens.issubset(set(query_tokens)):
                return col, val
    return None, None


def answer_query(query, df, numeric_cols, category_cols, date_cols):
    """
    Lightweight NL interpreter. Understands patterns like:
      - "show/plot <measure> by <category>"
      - "top 5 <category> by <measure>"
      - "trend of <measure>"
      - "average/sum/count/min/max of <measure>"
      - "distribution of <measure>"
      - "total <measure> in <value>"  (e.g. "total sales in south region")
    Returns (message, plotly_figure_or_None, dataframe_or_None)
    """
    q = query.lower().strip()
    q_tokens = tokenize(q)

    # ---- Detect a VALUE filter first (e.g. "south" -> Region == "South") ----
    filter_col, filter_val = find_value_filter(q_tokens, df, category_cols)
    working_df = df
    filter_note = ""
    if filter_col and filter_val is not None:
        working_df = df[df[filter_col] == filter_val]
        filter_note = f" where **{filter_col} = {filter_val}**"
        # remove the value's own words so they don't get mistaken for column names
        q_tokens = [t for t in q_tokens if t not in tokenize(str(filter_val))]

    meaningful_tokens = [t for t in q_tokens if t not in STOPWORDS]

    # top N pattern
    top_match = re.search(r"top\s+(\d+)", q)
    n = int(top_match.group(1)) if top_match else None

    # ---- detect measure (numeric column) via fuzzy word match ----
    measure = find_best_column_match(meaningful_tokens, numeric_cols)
    if measure is None and numeric_cols:
        # fall back to the business-relevant default rather than the first column
        measure = choose_primary_measure(df) or numeric_cols[0]

    # ---- detect category (only if explicitly referenced, not the filter column) ----
    remaining_cat_cols = [c for c in category_cols if c != filter_col]
    category = find_best_column_match(meaningful_tokens, remaining_cat_cols)

    # detect date
    date_col = date_cols[0] if date_cols else None

    df = working_df  # use the filtered data for everything below

    # AGGREGATION QUERIES
    agg_map = {"average": "mean", "avg": "mean", "mean": "mean",
               "sum": "sum", "total": "sum",
               "count": "count", "minimum": "min", "min": "min",
               "maximum": "max", "max": "max"}
    for word, func in agg_map.items():
        if word in q and measure:
            if df.empty:
                return f"No rows match{filter_note}.", None, None
            result = df[measure].agg(func)
            value_str = format_number(result) if func != "count" else f"{int(result):,}"
            msg = f"**{func.title()} of `{measure}`**{filter_note} = **{value_str}**"
            return msg, None, None

    # TREND
    if "trend" in q or "over time" in q:
        if date_col and measure:
            trend_data = (
                df.dropna(subset=[date_col])
                .groupby(date_col)[measure].sum()
                .reset_index().sort_values(date_col)
            )
            fig = px.line(trend_data, x=date_col, y=measure, markers=True,
                           template=PLOTLY_TEMPLATE, color_discrete_sequence=[PRIMARY])



# ===========================================================
# HEADER
# ===========================================================
st.markdown(
    """
    <div class="app-header">
        <h1>📊 AI Analytics Dashboard</h1>
        <p>Upload a dataset and instantly get KPIs, dynamic charts, and a built-in data assistant you can talk to.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ===========================================================
# SIDEBAR — UPLOAD
# ===========================================================
with st.sidebar:
    st.markdown("### 📁 Data Source")
    uploaded_file = st.file_uploader(
        "Upload Excel or CSV",
        type=["xlsx", "xls", "csv"],
        help="Supported formats: .xlsx, .xls, .csv",
    )
    st.markdown("---")

if uploaded_file is None:
    st.info("👈 Upload a file from the sidebar to build your dashboard.")
    c1, c2, c3, c4 = st.columns(4)
    for col, icon, title, desc in zip(
        [c1, c2, c3, c4],
        ["📤", "🧠", "📌", "💬"],
        ["Upload", "Auto-Analysis", "Smart KPIs", "Ask Your Data"],
        [
            "Drop in any Excel/CSV file.",
            "Columns are auto-classified as numeric, categorical, date or ID.",
            "Key metrics are generated automatically.",
            "Type plain-English questions to reshape charts.",
        ],
    ):
        with col:
            st.markdown(
                f"""<div class="kpi-card"><div style="font-size:1.6rem">{icon}</div>
                <b>{title}</b><br><span style="color:#636E72;font-size:0.85rem">{desc}</span></div>""",
                unsafe_allow_html=True,
            )
    st.stop()

# ===========================================================
# READ + PREP DATA
# ===========================================================
try:
    with st.spinner("Reading your file..."):
        df = read_uploaded_file(uploaded_file.getvalue(), uploaded_file.name)
        df = clean_column_names(df)
except Exception as e:
    st.error(f"Unable to read the file: {e}")
    st.stop()

if df.empty:
    st.warning("The uploaded file has no data.")
    st.stop()

date_columns = detect_date_columns(df)
id_columns = detect_id_columns(df)
for col in date_columns:
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        df[col] = pd.to_datetime(df[col], errors="coerce")

numeric_columns = df.select_dtypes(include=np.number).columns.tolist()
category_columns = choose_category_columns(df, id_columns)
primary_measure = choose_primary_measure(df)

# ===========================================================
# SIDEBAR — FILTERS (act on a copy: filtered_df)
# ===========================================================
with st.sidebar:
    st.markdown("### 🎚️ Filters")
    filtered_df = df.copy()

    if date_columns:
        dcol = date_columns[0]
        valid_dates = df[dcol].dropna()
        if not valid_dates.empty:
            min_d, max_d = valid_dates.min(), valid_dates.max()
            date_range = st.date_input("Date range", value=(min_d, max_d))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
                filtered_df = filtered_df[
                    (filtered_df[dcol] >= start) & (filtered_df[dcol] <= end)
                    | filtered_df[dcol].isna()
                ]

    for cat in category_columns[:3]:
        options = sorted(df[cat].dropna().unique().tolist())
        selected = st.multiselect(f"{cat}", options, default=[])
        if selected:
            filtered_df = filtered_df[filtered_df[cat].isin(selected)]

    st.markdown("---")
    st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** rows")
    csv_download = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered data", csv_download, "filtered_data.csv", "text/csv")

st.success(f"✅ **{uploaded_file.name}** — {len(filtered_df):,} rows × {len(df.columns):,} columns")

# ===========================================================
# TABS
# ===========================================================
tab_overview, tab_trends, tab_deepdive, tab_quality, tab_ask = st.tabs(
    ["📌 Overview", "📈 Trends", "🔍 Deep Dive", "🧹 Data Quality", "💬 Ask Your Data"]
)

# -----------------------------------------------------------
# TAB 1 — OVERVIEW (KPIs + primary charts)
# -----------------------------------------------------------
with tab_overview:
    st.markdown('<div class="section-title">Key Performance Indicators</div>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        kpi_card("Total Records", f"{len(filtered_df):,}")
    with k2:
        if id_columns:
            idc = id_columns[0]
            kpi_card(f"Unique {idc}", f"{filtered_df[idc].nunique():,}")
        else:
            kpi_card("Unique Rows", f"{filtered_df.drop_duplicates().shape[0]:,}")
    with k3:
        if primary_measure:
            kpi_card(f"Total {primary_measure}", format_number(filtered_df[primary_measure].sum()))
        else:
            kpi_card("Total Measure", "—")
    with k4:
        if primary_measure:
            kpi_card(f"Average {primary_measure}", format_number(filtered_df[primary_measure].mean()))
        else:
            kpi_card("Average Measure", "—")
    with k5:
        if primary_measure:
            kpi_card(f"Max {primary_measure}", format_number(filtered_df[primary_measure].max()))
        else:
            kpi_card("Max Measure", "—")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Dashboard Controls</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        selected_measure = st.selectbox(
            "Measure", numeric_columns,
            index=numeric_columns.index(primary_measure) if primary_measure in numeric_columns else 0,
        ) if numeric_columns else None
    with c2:
        selected_category = st.selectbox("Category", category_columns) if category_columns else None
    with c3:
        chart_type = st.radio("Chart style", ["Bar", "Pie", "Treemap"], horizontal=True)

    if selected_measure and selected_category:
        grouped = (
            filtered_df.groupby(selected_category, dropna=False)[selected_measure]
            .sum().reset_index().sort_values(selected_measure, ascending=False).head(15)
        )
        st.markdown(f'<div class="section-title">{selected_measure} by {selected_category}</div>', unsafe_allow_html=True)
        if chart_type == "Bar":
            fig = px.bar(grouped, x=selected_category, y=selected_measure, text_auto=".2s",
                         color=selected_category, color_discrete_sequence=COLOR_SEQUENCE,
                         template=PLOTLY_TEMPLATE)
            fig.update_layout(showlegend=False, height=450)
        elif chart_type == "Pie":
            fig = px.pie(grouped, names=selected_category, values=selected_measure, hole=0.45,
                         color_discrete_sequence=COLOR_SEQUENCE, template=PLOTLY_TEMPLATE)
            fig.update_layout(height=450)
        else:
            fig = px.treemap(grouped, path=[selected_category], values=selected_measure,
                              color=selected_measure, color_continuous_scale="Purples")
            fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-title">🏆 Top 10 Ranking</div>', unsafe_allow_html=True)
        st.dataframe(grouped.head(10), use_container_width=True, hide_index=True)

# -----------------------------------------------------------
# TAB 2 — TRENDS
# -----------------------------------------------------------
with tab_trends:
    if date_columns and numeric_columns:
        c1, c2 = st.columns(2)
        with c1:
            trend_measure = st.selectbox("Measure to trend", numeric_columns, key="trend_measure")
        with c2:
            trend_date = st.selectbox("Date column", date_columns, key="trend_date")

        freq_label = st.radio("Aggregate by", ["Day", "Week", "Month", "Year"], horizontal=True, index=2)
        # Use modern pandas offset aliases (pandas >= 2.2 deprecated "M"/"Y")
        freq_map = {"Day": "D", "Week": "W", "Month": "ME", "Year": "YE"}

        trend_data = filtered_df.dropna(subset=[trend_date, trend_measure]).copy()
        if trend_data.empty:
            st.info("No valid data available for the selected measure/date combination.")
        else:
            trend_data = (
                trend_data.set_index(trend_date)[trend_measure]
                .resample(freq_map[freq_label]).sum()
                .reset_index()
            )
            st.markdown(f'<div class="section-title">{trend_measure} Trend ({freq_label})</div>', unsafe_allow_html=True)
            fig = px.area(trend_data, x=trend_date, y=trend_measure, template=PLOTLY_TEMPLATE,
                           color_discrete_sequence=[PRIMARY])
            fig.update_traces(line=dict(width=3))
            fig.update_layout(height=460)
            st.plotly_chart(fig, use_container_width=True)

            # Rolling comparison
            if len(trend_data) > 1:
                latest = trend_data[trend_measure].iloc[-1]
                prior = trend_data[trend_measure].iloc[-2]
                change = ((latest - prior) / prior * 100) if prior != 0 else 0
                kpi_card(
                    f"Latest {freq_label} vs Previous",
                    format_number(latest),
                    delta=f"{change:+.1f}%",
                    delta_positive=change >= 0,
                )
    else:
        st.info("No date column detected in this dataset, so trend analysis isn't available.")

# -----------------------------------------------------------
# TAB 3 — DEEP DIVE (distribution, correlation, scatter)
# -----------------------------------------------------------
with tab_deepdive:
    st.markdown('<div class="section-title">Distribution</div>', unsafe_allow_html=True)
    if numeric_columns:
        dist_measure = st.selectbox("Column", numeric_columns, key="dist_measure")
        fig = px.histogram(filtered_df, x=dist_measure, nbins=30, marginal="box",
                            template=PLOTLY_TEMPLATE, color_discrete_sequence=[ACCENT])
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)

    if len(numeric_columns) >= 2:
        st.markdown('<div class="section-title">Correlation Heatmap</div>', unsafe_allow_html=True)
        corr = filtered_df[numeric_columns].corr(numeric_only=True)
        fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale="Purples",
                              template=PLOTLY_TEMPLATE, aspect="auto")
        fig_corr.update_layout(height=450)
        st.plotly_chart(fig_corr, use_container_width=True)

        st.markdown('<div class="section-title">Scatter Explorer</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            x_axis = st.selectbox("X axis", numeric_columns, index=0)
        with c2:
            y_axis = st.selectbox("Y axis", numeric_columns, index=min(1, len(numeric_columns) - 1))
        with c3:
            color_by = st.selectbox("Color by", ["None"] + category_columns)
        fig_scatter = px.scatter(
            filtered_df, x=x_axis, y=y_axis,
            color=None if color_by == "None" else color_by,
            template=PLOTLY_TEMPLATE, color_discrete_sequence=COLOR_SEQUENCE,
            opacity=0.75,
        )
        fig_scatter.update_layout(height=460)
        st.plotly_chart(fig_scatter, use_container_width=True)

# -----------------------------------------------------------
# TAB 4 — DATA QUALITY
# -----------------------------------------------------------
with tab_quality:
    st.markdown('<div class="section-title">Dataset Profile</div>', unsafe_allow_html=True)
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Rows", f"{len(filtered_df):,}")
    p2.metric("Columns", f"{len(df.columns):,}")
    p3.metric("Numeric Columns", len(numeric_columns))
    p4.metric("Date Columns", len(date_columns))

    st.markdown('<div class="section-title">Missing Values</div>', unsafe_allow_html=True)
    missing = filtered_df.isna().sum().reset_index()
    missing.columns = ["Column", "Missing Values"]
    missing["Missing %"] = (missing["Missing Values"] / len(filtered_df) * 100).round(2)
    missing = missing.sort_values("Missing Values", ascending=False)

    fig_missing = px.bar(missing[missing["Missing Values"] > 0], x="Column", y="Missing %",
                          template=PLOTLY_TEMPLATE, color_discrete_sequence=["#D63031"])
    if not missing[missing["Missing Values"] > 0].empty:
        fig_missing.update_layout(height=350)
        st.plotly_chart(fig_missing, use_container_width=True)
    else:
        st.info("🎉 No missing values detected in this dataset.")

    st.dataframe(missing, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">Data Preview</div>', unsafe_allow_html=True)
    st.dataframe(filtered_df.head(100), use_container_width=True, height=380)

# -----------------------------------------------------------
# TAB 5 — ASK YOUR DATA (Q&A)
# -----------------------------------------------------------
with tab_ask:
    st.markdown('<div class="section-title">💬 Ask Your Data</div>', unsafe_allow_html=True)
    st.caption(
        "Type a question in plain English to reshape the dashboard — e.g. "
        "*'show revenue by region'*, *'top 5 customers'*, *'trend of sales'*, "
        "*'average of premium'*, *'distribution of claim'*."
    )

    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []

    query = st.text_input("Ask a question about your data:", placeholder="e.g. show total sales by category")
    ask_col1, ask_col2 = st.columns([1, 5])
    with ask_col1:
        submitted = st.button("Ask ✨", use_container_width=True)

    if submitted and query.strip():
        message, fig, table = answer_query(query, filtered_df, numeric_columns, category_columns, date_columns)
        st.session_state.qa_history.insert(
            0,
            {"query": query, "message": message, "fig": fig, "table": table},
        )

    for idx, item in enumerate(st.session_state.qa_history):
        st.markdown(f'<div class="qa-answer">🗨️ <b>You asked:</b> "{item["query"]}"<br>🤖 {item["message"]}</div>',
                    unsafe_allow_html=True)
        if item["fig"] is not None:
            st.plotly_chart(item["fig"], use_container_width=True, key=f"qa_chart_{idx}")
        if item["table"] is not None:
            st.dataframe(item["table"], use_container_width=True, hide_index=True, key=f"qa_table_{idx}")
        st.markdown("---")

    if not st.session_state.qa_history:
        st.info("Ask your first question above to customize the dashboard on the fly!")

# ===========================================================
# FOOTER
# ===========================================================
st.markdown(
    """
    <div style="text-align:center; color:#B2BEC3; font-size:0.8rem; margin-top:2rem;">
        Built with ❤️ using Streamlit & Plotly — AI Analytics Dashboard
    </div>
    """,
    unsafe_allow_html=True,
)

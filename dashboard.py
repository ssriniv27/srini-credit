"""Streamlit dashboard for the Srini Credit project."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import streamlit as st

from credit_engine import (
    FinancialDataError,
    UnsupportedTickerError,
    analyze_company,
    create_credit_pdf,
)


st.set_page_config(
    page_title="Srini Credit",
    page_icon="📊",
    layout="wide",
)


try:
    API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error(
        "The FMP API key is missing. Add API_KEY to "
        ".streamlit/secrets.toml locally or to the app's Secrets settings "
        "on Streamlit Community Cloud."
    )
    st.stop()


@st.cache_data(show_spinner=False, ttl=900)
def run_analysis(ticker: str):
    """Run and temporarily cache one company analysis."""

    return analyze_company(ticker, API_KEY)


def create_pdf_bytes(result: dict) -> bytes:
    """Create the PDF in a temporary folder and return its bytes."""

    with TemporaryDirectory() as temporary_directory:
        pdf_path = create_credit_pdf(
            result,
            output_directory=temporary_directory,
        )
        return Path(pdf_path).read_bytes()


def get_memo_section(result: dict, section_name: str) -> str:
    """Retrieve one named memo section from the result."""

    for title, content in result["memo_sections"]:
        if title == section_name:
            return content

    return "Section unavailable."


def display_result(result: dict) -> None:
    """Display a completed Srini Credit analysis."""

    ticker = result["ticker"]
    company_name = result["company_name"]

    st.divider()
    st.subheader(f"{company_name} ({ticker})")
    st.caption(
        f"Scoring profile: {result['scoring_profile_name']} | "
        f"Financial warning score cap: {result['score_cap']}/100"
    )

    if result["model_scope_warning"]:
        st.info(result["model_scope_warning"])

    score_column, tier_column, trend_column, recommendation_column = st.columns(
        [1, 1, 1, 2]
    )

    with score_column:
        st.metric(
            "Final Score",
            f"{result['srinicredit_score']}/100",
        )

    with tier_column:
        st.metric(
            "Credit Tier",
            result["credit_tier"],
        )

    with trend_column:
        st.metric(
            "Trend Adjustment",
            f"{result['trend_adjustment']:+d}",
        )

    with recommendation_column:
        st.metric(
            "Lending Recommendation",
            result["lending_recommendation"],
        )

    category_rows = []

    for category_name, earned_points, maximum_points in result["category_scores"]:
        category_rows.append(
            {
                "Category": category_name,
                "Points": earned_points,
                "Maximum": maximum_points,
                "Percent of Maximum": round(
                    earned_points / maximum_points * 100,
                    1,
                ),
            }
        )

    category_frame = pd.DataFrame(category_rows)

    score_tab, market_tab, memo_tab, details_tab = st.tabs(
        [
            "Score Breakdown",
            "Market History",
            "Analyst Memo",
            "Detailed Data",
        ]
    )

    with score_tab:
        chart_column, table_column = st.columns([3, 2])

        with chart_column:
            st.markdown("#### Category Performance")
            st.bar_chart(
                category_frame,
                x="Category",
                y="Percent of Maximum",
            )

        with table_column:
            st.markdown("#### Category Scores")
            st.dataframe(
                category_frame,
                hide_index=True,
                width="stretch",
            )

        if result["score_cap_applied"]:
            st.caption(
                f"The uncapped score was "
                f"{result['uncapped_srinicredit_score']}/100 and was "
                f"limited to {result['score_cap']}/100 by the model's "
                f"financial-warning cap. Market warnings do not cap the score."
            )

        st.markdown("#### Executive Summary")
        st.write(get_memo_section(result, "Executive Summary"))

        st.markdown("#### Warning Signals")

        if result["critical_warning_signals"]:
            st.markdown("**Critical financial warnings**")
            for warning in result["critical_warning_signals"]:
                st.error(warning)

        if result["major_warning_signals"]:
            st.markdown("**Major financial warnings**")
            for warning in result["major_warning_signals"]:
                st.warning(warning)

        if result["informational_warning_signals"]:
            st.markdown("**Informational warnings**")
            for warning in result["informational_warning_signals"]:
                if warning != result["model_scope_warning"]:
                    st.info(warning)

        if not result["warning_signals"]:
            st.success("No warning signals were detected by the model.")

        st.markdown("#### Debt-Service Metrics")
        debt_metric_columns = st.columns(3)
        with debt_metric_columns[0]:
            st.metric(
                "Net Debt / EBITDA",
                result["net_debt_to_ebitda_text"],
            )
        with debt_metric_columns[1]:
            st.metric(
                "Interest Coverage",
                result["interest_coverage_text"],
            )
        with debt_metric_columns[2]:
            st.metric(
                "Operating Cash Flow / Debt",
                result["operating_cash_flow_to_debt_text"],
            )

    with market_tab:
        history_frame = pd.DataFrame(result["historical_data"])
        history_frame["date"] = pd.to_datetime(history_frame["date"])
        history_frame = history_frame.sort_values("date")

        st.markdown("#### Historical Share Price")
        st.line_chart(
            history_frame,
            x="date",
            y="price",
        )

        st.caption(
            "Equity-price history is included as a supplemental market-risk "
            "measure and is not the same as default risk."
        )

    with memo_tab:
        for section_title, section_content in result["memo_sections"]:
            with st.expander(
                section_title,
                expanded=section_title == "Executive Summary",
            ):
                st.write(section_content)

        st.markdown("#### Full Plain-Text Memo")
        st.text_area(
            "Memo",
            value=result["full_memo"],
            height=450,
            label_visibility="collapsed",
        )

    with details_tab:
        raw_data = result["raw"]

        with st.expander("Company Profile", expanded=True):
            st.json(raw_data["company"])

        with st.expander("Latest Income Statement"):
            st.json(raw_data["income_statement"])

        with st.expander("Latest Balance Sheet"):
            st.json(raw_data["balance_sheet"])

        with st.expander("Latest Cash-Flow Statement"):
            st.json(raw_data["cash_flow_statement"])

        with st.expander("Terminal-Style Detailed Output"):
            st.code(result["detailed_output"], language=None)

    st.divider()
    st.markdown("### Download Report")

    text_bytes = result["full_memo"].encode("utf-8")

    try:
        pdf_bytes = create_pdf_bytes(result)
    except OSError as error:
        pdf_bytes = None
        st.error(f"The PDF could not be created: {error}")

    text_column, pdf_column = st.columns(2)

    with text_column:
        st.download_button(
            label="Download Text Report",
            data=text_bytes,
            file_name=f"{ticker}_srini_credit_report.txt",
            mime="text/plain",
            width="stretch",
        )

    with pdf_column:
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes if pdf_bytes is not None else b"",
            file_name=f"{ticker}_srini_credit_report.pdf",
            mime="application/pdf",
            disabled=pdf_bytes is None,
            width="stretch",
        )


st.title("Srini Credit")
st.write(
    "Enter a supported stock ticker to generate a financial-credit screening "
    "score, risk analysis, historical trend review, and analyst report."
)
st.caption(
    "Srini Credit is an educational screening model, not an official credit "
    "rating or a substitute for professional underwriting."
)

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

with st.form("ticker_form"):
    ticker_input = st.text_input(
        "Stock ticker",
        value="NVDA",
        max_chars=12,
        placeholder="Example: NVDA",
    )

    analyze_button = st.form_submit_button(
        "Analyze Company",
        width="stretch",
    )

if analyze_button:
    ticker = ticker_input.strip().upper()
    st.session_state.analysis_result = None

    if not ticker:
        st.warning("Enter a stock ticker before running the analysis.")
    else:
        try:
            with st.spinner(f"Analyzing {ticker}..."):
                st.session_state.analysis_result = run_analysis(ticker)
        except UnsupportedTickerError:
            st.error(
                f"{ticker} is unsupported by this program or unavailable "
                "under the current FMP subscription."
            )
        except FinancialDataError as error:
            st.error(f"The analysis could not be completed: {error}")
        except Exception as error:
            st.error(
                "An unexpected error occurred. The technical message is shown "
                "below for debugging."
            )
            st.exception(error)

if st.session_state.analysis_result is not None:
    display_result(st.session_state.analysis_result)

"""Reusable analysis engine for the Srini Credit project."""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class UnsupportedTickerError(Exception):
    """Raised when FMP cannot provide every dataset required by the model."""


class FinancialDataError(Exception):
    """Raised when required financial values are missing or unusable."""


def is_valid_financial_number(value: Any) -> bool:
    """Return True when a value is a finite real number."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def format_currency(value: Any) -> str:
    """Format a valid number as whole-dollar currency."""

    if is_valid_financial_number(value):
        return f"${value:,.0f}"
    return "Unavailable"


def format_text(value: Any) -> str:
    """Convert a missing text value into a readable label."""

    if value is None or value == "":
        return "Unavailable"
    return str(value)


def safe_divide(numerator: Any, denominator: Any, calculation_name: str) -> float:
    """Divide two required financial values safely."""

    if not is_valid_financial_number(numerator):
        raise FinancialDataError(
            f"Unable to calculate {calculation_name}: the numerator is missing or invalid."
        )

    if not is_valid_financial_number(denominator):
        raise FinancialDataError(
            f"Unable to calculate {calculation_name}: the denominator is missing or invalid."
        )

    if denominator == 0:
        raise FinancialDataError(
            f"Unable to calculate {calculation_name}: the denominator is zero."
        )

    return float(numerator) / float(denominator)


def get_fmp_json(endpoint: str, ticker: str, api_key: str) -> list[dict[str, Any]]:
    """Retrieve a required nonempty JSON list from an FMP endpoint."""

    url = f"https://financialmodelingprep.com/stable/{endpoint}"
    params = {"symbol": ticker, "apikey": api_key}

    try:
        response = requests.get(url, params=params, timeout=20)
    except requests.RequestException as error:
        raise UnsupportedTickerError(
            f"Unable to retrieve {endpoint} data for {ticker}."
        ) from error

    if response.status_code != 200:
        raise UnsupportedTickerError(
            f"FMP returned HTTP {response.status_code} for {endpoint}."
        )

    try:
        data = response.json()
    except ValueError as error:
        raise UnsupportedTickerError(
            f"FMP returned unreadable data for {endpoint}."
        ) from error

    if not isinstance(data, list) or not data:
        raise UnsupportedTickerError(
            f"No usable {endpoint} data was returned for {ticker}."
        )

    if not all(isinstance(record, dict) for record in data):
        raise UnsupportedTickerError(
            f"FMP returned an unexpected data format for {endpoint}."
        )

    return data


def build_financial_history(
    statements: list[dict[str, Any]],
    fields: list[str],
) -> list[dict[str, Any]]:
    """Clean financial statements and sort them from oldest to newest."""

    cleaned_history: list[dict[str, Any]] = []

    for statement in statements:
        statement_date = statement.get("date")

        try:
            parsed_date = datetime.strptime(statement_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue

        cleaned_record: dict[str, Any] = {"date": parsed_date}
        has_valid_value = False

        for field in fields:
            value = statement.get(field)
            if is_valid_financial_number(value):
                cleaned_record[field] = float(value)
                has_valid_value = True
            else:
                cleaned_record[field] = None

        if has_valid_value:
            cleaned_history.append(cleaned_record)

    cleaned_history.sort(key=lambda record: record["date"])
    return cleaned_history


def get_financial_series(
    history: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    """Return valid dated values for one financial field."""

    return [
        {"date": record["date"], "value": record[field]}
        for record in history
        if record.get(field) is not None
    ]


def calculate_cagr(series: list[dict[str, Any]]) -> float | None:
    """Calculate CAGR when the oldest and newest values are positive."""

    if len(series) < 2:
        return None

    oldest_record = series[0]
    newest_record = series[-1]
    oldest_value = oldest_record["value"]
    newest_value = newest_record["value"]
    years = (newest_record["date"] - oldest_record["date"]).days / 365.25

    if years <= 0 or oldest_value <= 0 or newest_value <= 0:
        return None

    return (newest_value / oldest_value) ** (1 / years) - 1


def describe_amount_change(
    series: list[dict[str, Any]],
    financial_name: str,
) -> str:
    """Describe the change between the oldest and newest values."""

    if len(series) < 2:
        return (
            f"The historical {financial_name.lower()} trend could not be "
            f"calculated because fewer than two valid statements were available."
        )

    oldest_record = series[0]
    newest_record = series[-1]
    oldest_value = oldest_record["value"]
    newest_value = newest_record["value"]
    change = newest_value - oldest_value

    if change > 0:
        direction = "increased"
    elif change < 0:
        direction = "decreased"
    else:
        direction = "remained unchanged"

    return (
        f"{financial_name} {direction} from {format_currency(oldest_value)} on "
        f"{oldest_record['date'].strftime('%Y-%m-%d')} to "
        f"{format_currency(newest_value)} on "
        f"{newest_record['date'].strftime('%Y-%m-%d')}."
    )


def build_margin_series(
    statements: list[dict[str, Any]],
    income_field: str,
) -> list[dict[str, Any]]:
    """Calculate historical margins using revenue as the denominator."""

    margin_series: list[dict[str, Any]] = []

    for statement in statements:
        statement_date = statement.get("date")
        revenue_value = statement.get("revenue")
        income_value = statement.get(income_field)

        try:
            parsed_date = datetime.strptime(statement_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue

        if not is_valid_financial_number(revenue_value):
            continue
        if not is_valid_financial_number(income_value):
            continue
        if revenue_value == 0:
            continue

        margin_series.append(
            {"date": parsed_date, "value": income_value / revenue_value}
        )

    margin_series.sort(key=lambda record: record["date"])
    return margin_series


def describe_margin_change(
    series: list[dict[str, Any]],
    margin_name: str,
) -> str:
    """Describe the change between the oldest and newest margins."""

    if len(series) < 2:
        return (
            f"The historical {margin_name.lower()} trend could not be calculated "
            f"because fewer than two valid statements were available."
        )

    oldest_margin = series[0]["value"]
    newest_margin = series[-1]["value"]
    percentage_point_change = (newest_margin - oldest_margin) * 100

    if percentage_point_change > 0:
        direction = "expanded"
    elif percentage_point_change < 0:
        direction = "contracted"
    else:
        direction = "remained unchanged"

    return (
        f"The {margin_name.lower()} {direction} from {oldest_margin:.2%} to "
        f"{newest_margin:.2%}, representing a change of "
        f"{percentage_point_change:+.2f} percentage points."
    )


def _clean_historical_prices(
    historical_data: list[dict[str, Any]],
    ticker: str,
) -> list[dict[str, Any]]:
    """Validate historical prices and return them in chronological order."""

    cleaned_history: list[dict[str, Any]] = []

    for record in historical_data:
        date_text = record.get("date")
        price = record.get("price")

        if not is_valid_financial_number(price) or price <= 0:
            continue

        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except (TypeError, ValueError):
            continue

        cleaned_history.append({"date": date_text, "price": float(price)})

    cleaned_history.sort(key=lambda record: record["date"])

    if len(cleaned_history) < 3:
        raise FinancialDataError(
            f"Srini Credit cannot analyze {ticker}: not enough valid "
            f"historical price data was returned."
        )

    return cleaned_history



# -----------------------------------------------------------------------------
# Experimental industry scoring profiles
# -----------------------------------------------------------------------------
# These thresholds are internal Srini Credit calibration choices. They are not
# official agency methodologies or published default-probability standards.

SCORING_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default Corporate",
        "current_ratio": ((2.00, 10), (1.50, 8), (1.00, 5), (0.75, 2)),
        "quick_ratio": ((1.50, 10), (1.20, 8), (1.00, 6), (0.75, 3)),
        "debt_to_equity": ((0.25, 10), (0.50, 8), (1.00, 6), (1.50, 3), (2.00, 1)),
        "debt_to_ebitda": ((1.00, 15), (2.00, 12), (3.00, 9), (4.00, 6), (5.00, 3)),
        "ebitda_margin": ((0.30, 8), (0.20, 6), (0.10, 4)),
        "net_margin": ((0.20, 8), (0.10, 6), (0.05, 4)),
        "operating_cash_flow_margin": ((0.20, 8), (0.12, 6), (0.05, 4)),
        "free_cash_flow_margin": ((0.15, 8), (0.08, 6), (0.03, 4)),
        "liquidity_warning_threshold": 1.00,
        "debt_warning_threshold": 4.00,
        "description": (
            "General nonfinancial corporate thresholds are used because no "
            "specialized industry profile matched the company."
        ),
    },
    "technology": {
        "name": "Technology",
        "current_ratio": ((2.00, 10), (1.50, 8), (1.00, 5), (0.75, 2)),
        "quick_ratio": ((1.50, 10), (1.20, 8), (1.00, 6), (0.75, 3)),
        "debt_to_equity": ((0.25, 10), (0.50, 8), (1.00, 6), (1.50, 3), (2.00, 1)),
        "debt_to_ebitda": ((1.00, 15), (2.00, 12), (3.00, 9), (4.00, 6), (5.00, 3)),
        "ebitda_margin": ((0.35, 8), (0.25, 6), (0.15, 4)),
        "net_margin": ((0.25, 8), (0.15, 6), (0.08, 4)),
        "operating_cash_flow_margin": ((0.25, 8), (0.15, 6), (0.08, 4)),
        "free_cash_flow_margin": ((0.20, 8), (0.12, 6), (0.06, 4)),
        "liquidity_warning_threshold": 1.00,
        "debt_warning_threshold": 4.00,
        "cash_flow_liquidity_support": ((0.75, 14), (0.50, 12), (0.35, 10)),
        "description": (
            "Technology companies are evaluated with higher profitability and "
            "cash-flow expectations because many mature firms in the sector "
            "operate asset-light, high-margin business models."
        ),
    },
    "discount_retail": {
        "name": "Discount Retail",
        "current_ratio": ((1.30, 10), (1.00, 8), (0.80, 6), (0.65, 3)),
        "quick_ratio": ((0.80, 10), (0.60, 8), (0.40, 6), (0.20, 3)),
        "debt_to_equity": ((0.25, 10), (0.50, 8), (1.00, 6), (1.50, 3), (2.00, 1)),
        "debt_to_ebitda": ((1.00, 15), (2.00, 12), (3.00, 9), (4.00, 6), (5.00, 3)),
        "ebitda_margin": ((0.10, 8), (0.07, 6), (0.04, 4)),
        "net_margin": ((0.05, 8), (0.035, 6), (0.02, 4)),
        "operating_cash_flow_margin": ((0.08, 8), (0.05, 6), (0.03, 4)),
        "free_cash_flow_margin": ((0.05, 8), (0.03, 6), (0.015, 4)),
        "liquidity_warning_threshold": 0.75,
        "debt_warning_threshold": 4.00,
        "ocf_to_debt_liquidity_support": ((0.75, 14), (0.50, 12), (0.30, 10), (0.20, 8)),
        "description": (
            "Discount retailers are evaluated with lower liquidity and margin "
            "thresholds to reflect rapid inventory turnover and high-volume, "
            "low-margin operating models."
        ),
    },
    "consumer_staples": {
        "name": "Consumer Staples",
        "current_ratio": ((1.50, 10), (1.20, 8), (0.90, 5), (0.70, 2)),
        "quick_ratio": ((1.00, 10), (0.80, 8), (0.60, 6), (0.40, 3)),
        "debt_to_equity": ((0.25, 10), (0.50, 8), (1.00, 6), (1.50, 3), (2.00, 1)),
        "debt_to_ebitda": ((1.00, 15), (2.00, 12), (3.00, 9), (4.00, 6), (5.00, 3)),
        "ebitda_margin": ((0.25, 8), (0.18, 6), (0.10, 4)),
        "net_margin": ((0.15, 8), (0.10, 6), (0.05, 4)),
        "operating_cash_flow_margin": ((0.15, 8), (0.10, 6), (0.05, 4)),
        "free_cash_flow_margin": ((0.10, 8), (0.07, 6), (0.03, 4)),
        "liquidity_warning_threshold": 0.80,
        "debt_warning_threshold": 4.00,
        "description": (
            "Consumer-staples companies are evaluated with thresholds that "
            "recognize stable demand, moderate margins, and working-capital "
            "structures that can differ from technology firms."
        ),
    },
    "telecommunications": {
        "name": "Telecommunications",
        "current_ratio": ((1.20, 10), (1.00, 8), (0.75, 5), (0.60, 2)),
        "quick_ratio": ((1.00, 10), (0.80, 8), (0.60, 6), (0.40, 3)),
        "debt_to_equity": ((0.50, 10), (1.00, 8), (1.50, 5), (2.00, 3), (2.50, 1)),
        "debt_to_ebitda": ((1.50, 15), (2.00, 12), (2.50, 9), (3.00, 6), (3.50, 3)),
        "interest_coverage": ((8.0, 5), (6.0, 4), (4.0, 3), (3.0, 2), (2.0, 1)),
        "ebitda_margin": ((0.30, 8), (0.22, 6), (0.15, 4)),
        "net_margin": ((0.12, 8), (0.07, 6), (0.03, 4)),
        "operating_cash_flow_margin": ((0.25, 8), (0.18, 6), (0.10, 4)),
        "free_cash_flow_margin": ((0.15, 8), (0.10, 6), (0.05, 4)),
        "liquidity_warning_threshold": 0.75,
        "debt_warning_threshold": 3.25,
        "description": (
            "Telecommunications companies are evaluated with recurring cash-flow "
            "strength in mind, but leverage and debt-service thresholds are kept "
            "strict because large structural debt burdens can materially reduce "
            "financial flexibility."
        ),
    },
    "energy": {
        "name": "Integrated Energy",
        "current_ratio": ((1.50, 10), (1.20, 8), (1.00, 5), (0.75, 2)),
        "quick_ratio": ((1.20, 10), (1.00, 8), (0.80, 6), (0.60, 3)),
        "debt_to_equity": ((0.25, 10), (0.50, 8), (1.00, 6), (1.50, 3), (2.00, 1)),
        "debt_to_ebitda": ((1.00, 15), (2.00, 12), (3.00, 9), (4.00, 6), (5.00, 3)),
        "ebitda_margin": ((0.25, 8), (0.18, 6), (0.10, 4)),
        "net_margin": ((0.15, 8), (0.08, 6), (0.04, 4)),
        "operating_cash_flow_margin": ((0.20, 8), (0.12, 6), (0.06, 4)),
        "free_cash_flow_margin": ((0.12, 8), (0.07, 6), (0.03, 4)),
        "liquidity_warning_threshold": 0.90,
        "debt_warning_threshold": 4.50,
        "description": (
            "Integrated energy companies are evaluated with thresholds that "
            "recognize commodity cyclicality and capital-intensive operations."
        ),
    },
}


def _score_higher_is_better(
    value: float,
    bands: tuple[tuple[float, int], ...],
    positive_fallback: int = 0,
) -> int:
    """Score a metric where larger values are generally stronger."""

    for minimum_value, points in bands:
        if value >= minimum_value:
            return points

    if value > 0:
        return positive_fallback
    return 0


def _score_lower_is_better(
    value: float,
    bands: tuple[tuple[float, int], ...],
) -> int:
    """Score a metric where smaller values are generally stronger."""

    for maximum_value, points in bands:
        if value <= maximum_value:
            return points
    return 0


def _select_scoring_profile(sector: str, industry: str) -> tuple[str, dict[str, Any]]:
    """Select an experimental scoring profile from FMP sector/industry text."""

    sector_text = sector.lower()
    industry_text = industry.lower()

    if "discount stores" in industry_text:
        key = "discount_retail"
    elif "telecommunication" in industry_text:
        key = "telecommunications"
    elif sector_text == "consumer defensive":
        key = "consumer_staples"
    elif sector_text == "energy" or "oil & gas" in industry_text:
        key = "energy"
    elif sector_text == "technology":
        key = "technology"
    else:
        key = "default"

    return key, SCORING_PROFILES[key]


def _classify_model_suitability(
    sector: str,
    industry: str,
    scoring_profile_key: str,
) -> tuple[str, str]:
    """Classify how appropriate the current Srini Credit model is."""

    sector_text = sector.lower()
    industry_text = industry.lower()

    if sector_text == "financial services" or any(
        term in industry_text
        for term in ("bank", "insurance", "asset management", "credit services")
    ):
        return (
            "Unsupported business model",
            "Banks, insurers, and other financial institutions require capital, "
            "reserve, asset-quality, and regulatory ratios that are not included "
            "in the standard Srini Credit framework.",
        )

    if any(
        term in industry_text
        for term in ("healthcare plans", "managed care", "health insurance")
    ):
        return (
            "Limited suitability",
            "Health insurers and managed-care companies have regulated capital, "
            "claims, reserve, and insurance-liability dynamics that are only "
            "partially captured by ordinary corporate ratios.",
        )

    if (
        "auto - manufacturers" in industry_text
        or "automobile manufacturers" in industry_text
    ):
        return (
            "Limited suitability",
            "Automakers may include captive-finance operations, so consolidated "
            "debt and EBITDA can be difficult to compare with ordinary industrial "
            "companies.",
        )

    if scoring_profile_key != "default":
        return (
            "Specialized profile",
            "An industry-adjusted Srini Credit profile is available for this "
            "company's business model.",
        )

    return (
        "Standard model",
        "The general nonfinancial corporate framework is used for this company.",
    )


def _get_model_scope_warning(
    model_suitability: str,
    model_suitability_reason: str,
) -> str | None:
    """Return a visible warning when model suitability is limited."""

    if model_suitability in {"Limited suitability", "Unsupported business model"}:
        return (
            f"Model-suitability warning: {model_suitability_reason} "
            "The numeric Srini Credit score should be treated as preliminary "
            "rather than definitive."
        )

    return None


def _has_sustained_decline(
    series: list[dict[str, Any]],
    minimum_total_decline: float = 0.10,
) -> bool:
    """Return True after two consecutive, material annual declines."""

    if len(series) < 3:
        return False

    recent_values = [record["value"] for record in series[-3:]]
    consecutive_declines = (
        recent_values[0] > recent_values[1] > recent_values[2]
    )
    baseline = abs(recent_values[0])

    if not consecutive_declines:
        return False
    if baseline == 0:
        return recent_values[-1] < recent_values[0]

    total_decline = (recent_values[0] - recent_values[-1]) / baseline
    return total_decline >= minimum_total_decline


def _has_sustained_increase(
    series: list[dict[str, Any]],
    minimum_total_increase: float = 0.25,
) -> bool:
    """Return True after two consecutive, material annual increases."""

    if len(series) < 3:
        return False

    recent_values = [record["value"] for record in series[-3:]]
    consecutive_increases = (
        recent_values[0] < recent_values[1] < recent_values[2]
    )
    baseline = abs(recent_values[0])

    if not consecutive_increases:
        return False
    if baseline == 0:
        return recent_values[-1] > recent_values[0]

    total_increase = (recent_values[-1] - recent_values[0]) / baseline
    return total_increase >= minimum_total_increase


def _has_sustained_absolute_decline(
    series: list[dict[str, Any]],
    minimum_drop: float,
) -> bool:
    """Return True when a ratio falls twice in a row by a material amount."""

    if len(series) < 3:
        return False

    recent_values = [record["value"] for record in series[-3:]]
    return (
        recent_values[0] > recent_values[1] > recent_values[2]
        and recent_values[0] - recent_values[-1] >= minimum_drop
    )

def analyze_company(ticker: str, api_key: str) -> dict[str, Any]:
    """Run the complete Srini Credit analysis and return all report data."""

    ticker = ticker.strip().upper()
    if not ticker:
        raise UnsupportedTickerError("No ticker was entered.")

    profile_data = get_fmp_json("profile", ticker, api_key)
    income_data = get_fmp_json("income-statement", ticker, api_key)
    balance_data = get_fmp_json("balance-sheet-statement", ticker, api_key)
    cash_flow_data = get_fmp_json("cash-flow-statement", ticker, api_key)
    raw_historical_data = get_fmp_json(
        "historical-price-eod/light", ticker, api_key
    )

    company = profile_data[0]
    income_statement = income_data[0]
    balance_sheet = balance_data[0]
    cash_flow_statement = cash_flow_data[0]

    # Safe company-profile values
    company_name = company.get("companyName") or ticker
    sector = company.get("sector") or "Unavailable"
    industry = company.get("industry") or "Unavailable"
    country = company.get("country") or "Unavailable"
    exchange_name = (
        company.get("exchangeFullName")
        or company.get("exchange")
        or "Unavailable"
    )
    ceo = company.get("ceo") or "Unavailable"

    scoring_profile_key, scoring_profile = _select_scoring_profile(
        sector, industry
    )
    scoring_profile_name = scoring_profile["name"]
    scoring_profile_description = scoring_profile["description"]
    model_suitability, model_suitability_reason = _classify_model_suitability(
        sector,
        industry,
        scoring_profile_key,
    )
    model_scope_warning = _get_model_scope_warning(
        model_suitability,
        model_suitability_reason,
    )

    stock_price = company.get("price")
    stock_price_text = (
        f"${stock_price:,.2f}"
        if is_valid_financial_number(stock_price)
        else "Unavailable"
    )

    market_cap = company.get("marketCap")
    market_cap_text = format_currency(market_cap)

    employee_count = company.get("fullTimeEmployees")
    employee_count_text = (
        f"{employee_count:,.0f}"
        if is_valid_financial_number(employee_count)
        else "Unavailable"
    )

    beta_value = company.get("beta")
    if is_valid_financial_number(beta_value):
        beta: float | None = float(beta_value)
        beta_text = f"{beta:.2f}"
    else:
        beta = None
        beta_text = "Unavailable"

    # Safe statement display values
    income_fiscal_year = format_text(income_statement.get("fiscalYear"))
    income_period = format_text(income_statement.get("period"))
    income_date = format_text(income_statement.get("date"))
    revenue_text = format_currency(income_statement.get("revenue"))
    ebitda_text = format_currency(income_statement.get("ebitda"))
    net_income_text = format_currency(income_statement.get("netIncome"))

    balance_fiscal_year = format_text(balance_sheet.get("fiscalYear"))
    balance_date = format_text(balance_sheet.get("date"))
    cash_text = format_currency(balance_sheet.get("cashAndCashEquivalents"))
    cash_and_investments_text = format_currency(
        balance_sheet.get("cashAndShortTermInvestments")
    )
    current_assets_text = format_currency(balance_sheet.get("totalCurrentAssets"))
    current_liabilities_text = format_currency(
        balance_sheet.get("totalCurrentLiabilities")
    )
    total_assets_text = format_currency(balance_sheet.get("totalAssets"))
    total_liabilities_text = format_currency(balance_sheet.get("totalLiabilities"))
    total_debt_text = format_currency(balance_sheet.get("totalDebt"))
    net_debt_text = format_currency(balance_sheet.get("netDebt"))
    equity_text = format_currency(balance_sheet.get("totalStockholdersEquity"))

    cash_flow_fiscal_year = format_text(cash_flow_statement.get("fiscalYear"))
    cash_flow_date = format_text(cash_flow_statement.get("date"))
    operating_cash_flow_text = format_currency(
        cash_flow_statement.get("operatingCashFlow")
    )
    capital_expenditure_text = format_currency(
        cash_flow_statement.get("capitalExpenditure")
    )
    free_cash_flow_text = format_currency(cash_flow_statement.get("freeCashFlow"))

    # Financial ratios
    current_ratio = safe_divide(
        balance_sheet.get("totalCurrentAssets"),
        balance_sheet.get("totalCurrentLiabilities"),
        "current ratio",
    )

    cash_and_investments = balance_sheet.get("cashAndShortTermInvestments")
    receivables = balance_sheet.get("netReceivables")
    if not is_valid_financial_number(cash_and_investments):
        raise FinancialDataError(
            "Unable to calculate quick ratio: cash and short-term investments "
            "are missing or invalid."
        )
    if not is_valid_financial_number(receivables):
        raise FinancialDataError(
            "Unable to calculate quick ratio: net receivables are missing or invalid."
        )

    quick_ratio = safe_divide(
        cash_and_investments + receivables,
        balance_sheet.get("totalCurrentLiabilities"),
        "quick ratio",
    )

    revenue = income_statement.get("revenue")
    net_income = income_statement.get("netIncome")
    ebitda = income_statement.get("ebitda")
    operating_income = income_statement.get("operatingIncome")
    interest_expense = income_statement.get("interestExpense")
    total_debt = balance_sheet.get("totalDebt")
    reported_net_debt = balance_sheet.get("netDebt")
    shareholders_equity = balance_sheet.get("totalStockholdersEquity")
    operating_cash_flow = cash_flow_statement.get("operatingCashFlow")
    free_cash_flow = cash_flow_statement.get("freeCashFlow")

    required_values = {
        "revenue": revenue,
        "net income": net_income,
        "EBITDA": ebitda,
        "total debt": total_debt,
        "shareholders' equity": shareholders_equity,
        "operating cash flow": operating_cash_flow,
        "free cash flow": free_cash_flow,
    }
    for value_name, value in required_values.items():
        if not is_valid_financial_number(value):
            raise FinancialDataError(
                f"Required value '{value_name}' is missing or invalid."
            )

    if is_valid_financial_number(reported_net_debt):
        net_debt = float(reported_net_debt)
    else:
        net_debt = float(total_debt) - float(cash_and_investments)

    if net_debt < 0:
        net_debt_text = (
            f"Net cash position ({format_currency(abs(net_debt))} excess cash)"
        )
    else:
        net_debt_text = format_currency(net_debt)

    if shareholders_equity <= 0:
        debt_to_equity = float("inf")
        debt_to_equity_text = (
            "Not meaningful because shareholders' equity is zero or negative"
        )
    else:
        debt_to_equity = total_debt / shareholders_equity
        debt_to_equity_text = f"{debt_to_equity:.2f}"

    if ebitda <= 0:
        debt_to_ebitda = float("inf")
        net_debt_to_ebitda = float("inf")
        debt_to_ebitda_text = (
            "Not meaningful because EBITDA is zero or negative"
        )
        net_debt_to_ebitda_text = debt_to_ebitda_text
    else:
        debt_to_ebitda = total_debt / ebitda
        net_debt_to_ebitda = net_debt / ebitda
        debt_to_ebitda_text = f"{debt_to_ebitda:.2f}"
        if net_debt <= 0:
            net_debt_to_ebitda_text = "Net cash position"
        else:
            net_debt_to_ebitda_text = f"{net_debt_to_ebitda:.2f}"

    if (
        is_valid_financial_number(operating_income)
        and is_valid_financial_number(interest_expense)
    ):
        interest_cost = abs(float(interest_expense))
        if interest_cost == 0:
            interest_coverage = (
                float("inf") if operating_income > 0 else 0.0
            )
        else:
            interest_coverage = float(operating_income) / interest_cost
    else:
        interest_coverage = None

    if interest_coverage is None:
        interest_coverage_text = "Unavailable"
    elif math.isinf(interest_coverage):
        interest_coverage_text = "No material interest expense"
    else:
        interest_coverage_text = f"{interest_coverage:.2f}x"

    if total_debt <= 0:
        operating_cash_flow_to_debt = float("inf")
        operating_cash_flow_to_debt_text = "No debt"
    else:
        operating_cash_flow_to_debt = operating_cash_flow / total_debt
        operating_cash_flow_to_debt_text = (
            f"{operating_cash_flow_to_debt:.2%}"
        )

    operating_cash_flow_to_current_liabilities = safe_divide(
        operating_cash_flow,
        balance_sheet.get("totalCurrentLiabilities"),
        "operating cash flow to current liabilities",
    )
    operating_cash_flow_to_current_liabilities_text = (
        f"{operating_cash_flow_to_current_liabilities:.2%}"
    )

    ebitda_margin = safe_divide(ebitda, revenue, "EBITDA margin")
    net_margin = safe_divide(net_income, revenue, "net margin")

    if shareholders_equity <= 0:
        return_on_equity = float("-inf")
        return_on_equity_text = (
            "Not meaningful because shareholders' equity is zero or negative"
        )
    else:
        return_on_equity = safe_divide(
            net_income, shareholders_equity, "return on equity"
        )
        return_on_equity_text = f"{return_on_equity:.2%}"

    operating_cash_flow_margin = safe_divide(
        operating_cash_flow, revenue, "operating cash-flow margin"
    )
    free_cash_flow_margin = safe_divide(
        free_cash_flow, revenue, "free cash-flow margin"
    )
    cash_conversion_ratio = (
        operating_cash_flow / net_income if net_income > 0 else 0.0
    )

    # Historical market calculations
    historical_data = _clean_historical_prices(raw_historical_data, ticker)
    oldest_price = historical_data[0]["price"]
    newest_price = historical_data[-1]["price"]
    oldest_date = datetime.strptime(historical_data[0]["date"], "%Y-%m-%d")
    newest_date = datetime.strptime(historical_data[-1]["date"], "%Y-%m-%d")
    years = (newest_date - oldest_date).days / 365.25

    if years <= 0:
        raise FinancialDataError(
            f"Srini Credit cannot analyze {ticker}: the historical date range is invalid."
        )

    total_return = newest_price / oldest_price - 1
    annualized_return = (newest_price / oldest_price) ** (1 / years) - 1
    prices = [record["price"] for record in historical_data]
    daily_returns = [
        prices[index] / prices[index - 1] - 1
        for index in range(1, len(prices))
    ]

    if len(daily_returns) < 2:
        raise FinancialDataError(
            f"Srini Credit cannot analyze {ticker}: not enough daily returns are available."
        )

    daily_volatility = statistics.stdev(daily_returns)
    annualized_volatility = daily_volatility * math.sqrt(252)

    running_peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        running_peak = max(running_peak, price)
        drawdown = price / running_peak - 1
        max_drawdown = min(max_drawdown, drawdown)

    # Historical financial trends
    income_trend_history = build_financial_history(
        income_data, ["revenue", "ebitda", "netIncome"]
    )
    balance_trend_history = build_financial_history(balance_data, ["totalDebt"])
    cash_flow_trend_history = build_financial_history(
        cash_flow_data, ["operatingCashFlow", "freeCashFlow"]
    )

    revenue_series = get_financial_series(income_trend_history, "revenue")
    ebitda_series = get_financial_series(income_trend_history, "ebitda")
    net_income_series = get_financial_series(income_trend_history, "netIncome")
    total_debt_series = get_financial_series(balance_trend_history, "totalDebt")
    operating_cash_flow_series = get_financial_series(
        cash_flow_trend_history, "operatingCashFlow"
    )
    free_cash_flow_series = get_financial_series(
        cash_flow_trend_history, "freeCashFlow"
    )
    ebitda_margin_series = build_margin_series(income_data, "ebitda")
    net_margin_series = build_margin_series(income_data, "netIncome")

    revenue_cagr = calculate_cagr(revenue_series)
    if len(revenue_series) >= 2:
        oldest_revenue = revenue_series[0]["value"]
        newest_revenue = revenue_series[-1]["value"]
        if revenue_cagr is not None:
            if revenue_cagr >= 0.10:
                revenue_trend_description = "strong"
            elif revenue_cagr > 0:
                revenue_trend_description = "positive"
            elif revenue_cagr == 0:
                revenue_trend_description = "flat"
            else:
                revenue_trend_description = "negative"

            revenue_trend_text = (
                f"The company demonstrates a {revenue_trend_description} "
                f"historical revenue trend. Revenue changed from "
                f"{format_currency(oldest_revenue)} to "
                f"{format_currency(newest_revenue)}, representing a compound "
                f"annual growth rate of {revenue_cagr:.2%}."
            )
        else:
            revenue_trend_text = describe_amount_change(revenue_series, "Revenue")
    else:
        revenue_trend_text = (
            "The historical revenue trend could not be calculated because "
            "fewer than two valid income statements were available."
        )

    ebitda_cagr = calculate_cagr(ebitda_series)
    if len(ebitda_series) >= 2 and ebitda_cagr is not None:
        ebitda_trend_text = (
            f"EBITDA changed from {format_currency(ebitda_series[0]['value'])} "
            f"to {format_currency(ebitda_series[-1]['value'])}, representing a "
            f"compound annual growth rate of {ebitda_cagr:.2%}."
        )
    else:
        ebitda_trend_text = describe_amount_change(ebitda_series, "EBITDA")

    net_income_trend_text = describe_amount_change(net_income_series, "Net income")
    operating_cash_flow_trend_text = describe_amount_change(
        operating_cash_flow_series, "Operating cash flow"
    )
    free_cash_flow_trend_text = describe_amount_change(
        free_cash_flow_series, "Free cash flow"
    )

    debt_change_percentage: float | None = None
    if len(total_debt_series) >= 2:
        oldest_debt = total_debt_series[0]["value"]
        newest_debt = total_debt_series[-1]["value"]
        if oldest_debt > 0:
            debt_change_percentage = (newest_debt - oldest_debt) / oldest_debt
            if debt_change_percentage > 0:
                debt_direction = "increased"
            elif debt_change_percentage < 0:
                debt_direction = "decreased"
            else:
                debt_direction = "remained unchanged"
            debt_trend_text = (
                f"Total debt {debt_direction} from {format_currency(oldest_debt)} "
                f"to {format_currency(newest_debt)}, representing a change of "
                f"{debt_change_percentage:.2%}."
            )
        else:
            debt_trend_text = describe_amount_change(total_debt_series, "Total debt")
    else:
        debt_trend_text = (
            "The historical debt trend could not be calculated because fewer "
            "than two valid balance sheets were available."
        )

    ebitda_margin_trend_text = describe_margin_change(
        ebitda_margin_series, "EBITDA margin"
    )
    net_margin_trend_text = describe_margin_change(net_margin_series, "Net margin")

    historical_trends_text = (
        f"Revenue Trend\n{revenue_trend_text}\n\n"
        f"EBITDA Trend\n{ebitda_trend_text}\n\n"
        f"Net-Income Trend\n{net_income_trend_text}\n\n"
        f"Operating Cash-Flow Trend\n{operating_cash_flow_trend_text}\n\n"
        f"Free-Cash-Flow Trend\n{free_cash_flow_trend_text}\n\n"
        f"Debt Trend\n{debt_trend_text}\n\n"
        f"EBITDA-Margin Trend\n{ebitda_margin_trend_text}\n\n"
        f"Net-Margin Trend\n{net_margin_trend_text}"
    )

    # Category scoring using the selected industry profile
    current_ratio_score = _score_higher_is_better(
        current_ratio,
        scoring_profile["current_ratio"],
    )
    quick_ratio_score = _score_higher_is_better(
        quick_ratio,
        scoring_profile["quick_ratio"],
    )
    conventional_liquidity_score = current_ratio_score + quick_ratio_score
    liquidity_score = conventional_liquidity_score
    liquidity_support_applied = False
    liquidity_support_note: str | None = None

    if scoring_profile_key == "technology":
        cash_flow_liquidity_score = _score_higher_is_better(
            operating_cash_flow_to_current_liabilities,
            scoring_profile["cash_flow_liquidity_support"],
        )
        if cash_flow_liquidity_score > liquidity_score:
            liquidity_score = cash_flow_liquidity_score
            liquidity_support_applied = True
            liquidity_support_note = (
                "Technology liquidity received cash-flow support because "
                f"operating cash flow equals "
                f"{operating_cash_flow_to_current_liabilities_text} of current "
                "liabilities."
            )

    elif scoring_profile_key == "discount_retail":
        cash_flow_liquidity_score = _score_higher_is_better(
            operating_cash_flow_to_debt,
            scoring_profile["ocf_to_debt_liquidity_support"],
        )
        if cash_flow_liquidity_score > liquidity_score:
            liquidity_score = cash_flow_liquidity_score
            liquidity_support_applied = True
            liquidity_support_note = (
                "Discount-retail liquidity received cash-flow support because "
                f"operating cash flow equals {operating_cash_flow_to_debt_text} "
                "of total debt, reducing reliance on static working-capital "
                "ratios alone."
            )

    debt_to_equity_raw_score = _score_lower_is_better(
        debt_to_equity,
        scoring_profile["debt_to_equity"],
    )
    net_debt_to_ebitda_raw_score = _score_lower_is_better(
        net_debt_to_ebitda,
        scoring_profile["debt_to_ebitda"],
    )

    debt_to_equity_score = round(debt_to_equity_raw_score * 8 / 10)
    net_debt_to_ebitda_score = round(
        net_debt_to_ebitda_raw_score * 12 / 15
    )

    if interest_coverage is None:
        gross_debt_fallback_score = _score_lower_is_better(
            debt_to_ebitda,
            scoring_profile["debt_to_ebitda"],
        )
        interest_coverage_score = round(
            gross_debt_fallback_score * 5 / 15
        )
        interest_coverage_scoring_note = (
            "Interest coverage was unavailable, so gross debt-to-EBITDA "
            "was used as a fallback for five leverage points."
        )
    else:
        interest_coverage_bands = scoring_profile.get(
            "interest_coverage",
            ((8.0, 5), (5.0, 4), (3.0, 3), (2.0, 2), (1.5, 1)),
        )
        interest_coverage_score = _score_higher_is_better(
            interest_coverage,
            interest_coverage_bands,
        )
        interest_coverage_scoring_note = None

    leverage_score = (
        debt_to_equity_score
        + net_debt_to_ebitda_score
        + interest_coverage_score
    )

    ebitda_margin_score = _score_higher_is_better(
        ebitda_margin,
        scoring_profile["ebitda_margin"],
        positive_fallback=2,
    )
    net_margin_score = _score_higher_is_better(
        net_margin,
        scoring_profile["net_margin"],
        positive_fallback=2,
    )

    if return_on_equity >= 0.20:
        return_on_equity_score = 4
    elif return_on_equity >= 0.12:
        return_on_equity_score = 3
    elif return_on_equity >= 0.05:
        return_on_equity_score = 2
    elif return_on_equity > 0:
        return_on_equity_score = 1
    else:
        return_on_equity_score = 0
    profitability_score = (
        ebitda_margin_score + net_margin_score + return_on_equity_score
    )

    operating_cash_flow_margin_score = _score_higher_is_better(
        operating_cash_flow_margin,
        scoring_profile["operating_cash_flow_margin"],
        positive_fallback=2,
    )
    free_cash_flow_margin_score = _score_higher_is_better(
        free_cash_flow_margin,
        scoring_profile["free_cash_flow_margin"],
        positive_fallback=2,
    )

    if cash_conversion_ratio >= 1.0:
        cash_conversion_score = 4
    elif cash_conversion_ratio >= 0.80:
        cash_conversion_score = 3
    elif cash_conversion_ratio >= 0.50:
        cash_conversion_score = 2
    elif cash_conversion_ratio > 0:
        cash_conversion_score = 1
    else:
        cash_conversion_score = 0
    cash_flow_score = (
        operating_cash_flow_margin_score
        + free_cash_flow_margin_score
        + cash_conversion_score
    )

    if beta is None:
        beta_score = 0
    elif beta <= 0.80:
        beta_score = 5
    elif beta <= 1.10:
        beta_score = 4
    elif beta <= 1.50:
        beta_score = 3
    elif beta <= 2.00:
        beta_score = 1
    else:
        beta_score = 0

    if annualized_volatility <= 0.20:
        volatility_score = 5
    elif annualized_volatility <= 0.30:
        volatility_score = 4
    elif annualized_volatility <= 0.40:
        volatility_score = 3
    elif annualized_volatility <= 0.50:
        volatility_score = 2
    elif annualized_volatility <= 0.60:
        volatility_score = 1
    else:
        volatility_score = 0

    if max_drawdown >= -0.20:
        drawdown_score = 5
    elif max_drawdown >= -0.35:
        drawdown_score = 4
    elif max_drawdown >= -0.50:
        drawdown_score = 3
    elif max_drawdown >= -0.65:
        drawdown_score = 1
    else:
        drawdown_score = 0
    market_risk_score = beta_score + volatility_score + drawdown_score

    # Historical trend score adjustment
    trend_adjustment = 0
    if revenue_cagr is not None:
        if revenue_cagr >= 0.10:
            trend_adjustment += 2
        elif revenue_cagr > 0:
            trend_adjustment += 1
        elif revenue_cagr < 0:
            trend_adjustment -= 2

    if len(ebitda_series) >= 2:
        if ebitda_series[-1]["value"] > ebitda_series[0]["value"]:
            trend_adjustment += 1
        elif ebitda_series[-1]["value"] < ebitda_series[0]["value"]:
            trend_adjustment -= 1

    if len(free_cash_flow_series) >= 2:
        if free_cash_flow_series[-1]["value"] > free_cash_flow_series[0]["value"]:
            trend_adjustment += 1
        elif free_cash_flow_series[-1]["value"] < free_cash_flow_series[0]["value"]:
            trend_adjustment -= 1

    if debt_change_percentage is not None:
        if debt_change_percentage <= -0.10:
            trend_adjustment += 1
        elif debt_change_percentage > 0.25:
            trend_adjustment -= 1

    if len(net_margin_series) >= 2:
        net_margin_change = (
            net_margin_series[-1]["value"] - net_margin_series[0]["value"]
        )
        if net_margin_change >= 0.03:
            trend_adjustment += 1
        elif net_margin_change <= -0.05:
            trend_adjustment -= 1

    trend_adjustment = max(-5, min(5, trend_adjustment))

    # Credit-focused weighted contributions. The raw category scoring
    # remains useful for diagnostics, but the final base score gives
    # more weight to leverage and cash generation and less weight to
    # equity-market volatility.
    weighted_liquidity_score = liquidity_score
    weighted_leverage_score = round(leverage_score * 30 / 25)
    weighted_profitability_score = profitability_score
    weighted_cash_flow_score = round(cash_flow_score * 25 / 20)
    weighted_market_risk_score = round(market_risk_score * 5 / 15)

    base_srinicredit_score = (
        weighted_liquidity_score
        + weighted_leverage_score
        + weighted_profitability_score
        + weighted_cash_flow_score
        + weighted_market_risk_score
    )
    uncapped_srinicredit_score = max(
        0, min(100, base_srinicredit_score + trend_adjustment)
    )

    # Warning signals classified by severity. Only critical and major
    # financial-credit warnings can cap the score. Market warnings are
    # informational because market risk is already represented in the model.
    critical_warning_signals: list[str] = []
    major_warning_signals: list[str] = []
    informational_warning_signals: list[str] = []
    market_warning_signals: list[str] = []

    if _has_sustained_decline(revenue_series, 0.05):
        major_warning_signals.append(
            "Revenue declined for two consecutive annual periods by a material amount."
        )
    if _has_sustained_decline(ebitda_series, 0.10):
        major_warning_signals.append(
            "EBITDA declined for two consecutive annual periods by a material amount."
        )
    if _has_sustained_decline(net_income_series, 0.10):
        major_warning_signals.append(
            "Net income declined for two consecutive annual periods by a material amount."
        )
    if _has_sustained_decline(operating_cash_flow_series, 0.10):
        major_warning_signals.append(
            "Operating cash flow declined for two consecutive annual periods."
        )
    if _has_sustained_decline(free_cash_flow_series, 0.10):
        major_warning_signals.append(
            "Free cash flow declined for two consecutive annual periods."
        )
    if _has_sustained_increase(total_debt_series, 0.25):
        major_warning_signals.append(
            "Total debt increased for two consecutive annual periods by more than 25%."
        )
    if _has_sustained_absolute_decline(ebitda_margin_series, 0.05):
        major_warning_signals.append(
            "The EBITDA margin contracted in two consecutive annual periods by at least five percentage points."
        )
    if _has_sustained_absolute_decline(net_margin_series, 0.05):
        major_warning_signals.append(
            "The net margin contracted in two consecutive annual periods by at least five percentage points."
        )

    if shareholders_equity <= 0:
        critical_warning_signals.append(
            "Shareholders' equity is zero or negative."
        )
    if ebitda <= 0:
        critical_warning_signals.append(
            "EBITDA is zero or negative, indicating weak operating earnings."
        )
    if free_cash_flow <= 0:
        critical_warning_signals.append(
            "Free cash flow is zero or negative."
        )
    if net_margin <= 0:
        critical_warning_signals.append(
            "The company reported a zero or negative net-profit margin."
        )

    severe_net_debt_threshold = (
        scoring_profile["debt_warning_threshold"] + 1.5
    )
    if net_debt_to_ebitda > severe_net_debt_threshold:
        critical_warning_signals.append(
            "Net debt is extremely high relative to EBITDA."
        )
    elif net_debt_to_ebitda > scoring_profile["debt_warning_threshold"]:
        major_warning_signals.append(
            "Net debt is high relative to EBITDA."
        )

    if interest_coverage is None:
        informational_warning_signals.append(
            "Interest coverage could not be calculated from the available income-statement fields."
        )
    elif interest_coverage < 1.0:
        critical_warning_signals.append(
            "Operating income does not fully cover reported interest expense."
        )
    elif interest_coverage < 2.0:
        major_warning_signals.append(
            "Interest coverage is below 2.0 times."
        )

    if current_ratio < scoring_profile["liquidity_warning_threshold"]:
        if liquidity_support_applied:
            informational_warning_signals.append(
                "Conventional short-term liquidity is below the profile threshold, "
                "but strong cash-flow coverage provided liquidity support in the "
                "selected industry model."
            )
        else:
            major_warning_signals.append(
                "Short-term liquidity is below the threshold used by the selected industry profile."
            )
    if (
        total_debt > 0
        and operating_cash_flow_to_debt < 0.15
        and operating_cash_flow > 0
    ):
        major_warning_signals.append(
            "Operating cash flow is less than 15% of total debt."
        )

    if annualized_volatility > 0.50:
        market_warning_signals.append(
            "The stock has experienced elevated historical volatility."
        )
    if max_drawdown < -0.50:
        market_warning_signals.append(
            "The stock has experienced a historical drawdown greater than 50%."
        )
    informational_warning_signals.extend(market_warning_signals)

    if model_scope_warning is not None:
        informational_warning_signals.append(model_scope_warning)

    critical_warning_count = len(critical_warning_signals)
    major_warning_count = len(major_warning_signals)
    informational_warning_count = len(informational_warning_signals)
    financial_warning_signals = (
        critical_warning_signals + major_warning_signals
    )
    financial_warning_count = len(financial_warning_signals)
    market_warning_count = len(market_warning_signals)

    if critical_warning_count > 0:
        financial_score_cap = 59
    elif major_warning_count >= 5:
        financial_score_cap = 69
    elif major_warning_count >= 3:
        financial_score_cap = 79
    elif major_warning_count == 2:
        financial_score_cap = 89
    elif major_warning_count == 1:
        financial_score_cap = 94
    else:
        financial_score_cap = 100

    score_cap = financial_score_cap
    srinicredit_score = min(uncapped_srinicredit_score, score_cap)
    score_cap_applied = srinicredit_score < uncapped_srinicredit_score

    # Model confidence measures data completeness separately from credit quality.
    minimum_statement_history = min(
        len(income_trend_history),
        len(balance_trend_history),
        len(cash_flow_trend_history),
    )
    confidence_points = 0
    confidence_notes: list[str] = []

    if minimum_statement_history >= 4:
        confidence_points += 2
    elif minimum_statement_history >= 3:
        confidence_points += 1
        confidence_notes.append(
            "Only three comparable annual statement periods were available."
        )
    else:
        confidence_notes.append(
            "Fewer than three comparable annual statement periods were available."
        )

    if interest_coverage is not None:
        confidence_points += 1
    else:
        confidence_notes.append(
            "Interest coverage could not be calculated from the available fields."
        )

    if beta is not None:
        confidence_points += 1
    else:
        confidence_notes.append("Beta was unavailable.")

    if len(historical_data) >= 252:
        confidence_points += 1
    else:
        confidence_notes.append(
            "Less than approximately one trading year of market history was available."
        )

    if model_suitability in {"Unsupported business model", "Limited suitability"}:
        confidence_level = "Low"
    elif confidence_points >= 4:
        confidence_level = "High"
    elif confidence_points >= 2:
        confidence_level = "Moderate"
    else:
        confidence_level = "Low"

    confidence_reason = (
        "Data coverage is strong for the selected model."
        if not confidence_notes
        else " ".join(confidence_notes)
    )

    if srinicredit_score >= 90:
        credit_tier = "Exceptional"
    elif srinicredit_score >= 80:
        credit_tier = "Strong"
    elif srinicredit_score >= 70:
        credit_tier = "Good"
    elif srinicredit_score >= 60:
        credit_tier = "Fair"
    elif srinicredit_score >= 50:
        credit_tier = "Weak"
    else:
        credit_tier = "High Risk"

    if model_suitability == "Unsupported business model":
        lending_recommendation = "Specialized credit model required"
    elif model_suitability == "Limited suitability":
        lending_recommendation = "Specialized analysis recommended"
    elif srinicredit_score >= 80:
        lending_recommendation = "Strong lending candidate"
    elif srinicredit_score >= 70:
        lending_recommendation = "Acceptable lending candidate"
    elif srinicredit_score >= 60:
        lending_recommendation = "Proceed with caution"
    else:
        lending_recommendation = "High-risk lending candidate"

    warning_signals = (
        critical_warning_signals
        + major_warning_signals
        + informational_warning_signals
    )

    warning_sections: list[str] = []
    if critical_warning_signals:
        warning_sections.append(
            "CRITICAL\n"
            + "\n".join(
                f"- {warning}" for warning in critical_warning_signals
            )
        )
    if major_warning_signals:
        warning_sections.append(
            "MAJOR\n"
            + "\n".join(
                f"- {warning}" for warning in major_warning_signals
            )
        )
    if informational_warning_signals:
        warning_sections.append(
            "INFORMATIONAL\n"
            + "\n".join(
                f"- {warning}" for warning in informational_warning_signals
            )
        )

    warning_signals_text = (
        "\n\n".join(warning_sections)
        if warning_sections
        else "- No warning signals were detected by the model."
    )

    # Memo analysis sections
    analyst_summary = (
        f"{company_name} ({ticker}) received a final Srini Credit score of "
        f"{srinicredit_score}/100, placing the company in the {credit_tier} "
        f"tier. The {scoring_profile_name} scoring profile was applied. Model "
        f"suitability is {model_suitability.lower()} with {confidence_level.lower()} "
        f"confidence. The score includes a base score of "
        f"{base_srinicredit_score}/100 and a "
        f"historical trend adjustment of {trend_adjustment:+d}. Based on the "
        f"model's evaluation of liquidity, "
        f"leverage, profitability, cash flow, market risk, and historical "
        f"trends, the company is classified as a "
        f"{lending_recommendation.lower()}."
    )

    company_overview = (
        f"{company_name} operates in the {industry} industry within the "
        f"{sector} sector. The company is headquartered in {country} and "
        f"trades on the {exchange_name}. Its reported market capitalization "
        f"is {market_cap_text}."
    )

    model_suitability_analysis = (
        f"Model Suitability: {model_suitability}. Confidence: {confidence_level}. "
        f"{model_suitability_reason} {confidence_reason}"
    )

    scoring_profile_analysis = (
        f"Srini Credit applied the {scoring_profile_name} profile. "
        f"{scoring_profile_description} These thresholds are experimental "
        f"internal calibration choices and should be validated against a "
        f"larger sample and external credit outcomes."
    )

    if current_ratio >= 2.0 and quick_ratio >= 1.5:
        liquidity_description = "strong"
        liquidity_conclusion = (
            "The company appears well positioned to meet its short-term "
            "obligations using current and highly liquid assets."
        )
    elif current_ratio >= 1.0 and quick_ratio >= 1.0:
        liquidity_description = "adequate"
        liquidity_conclusion = (
            "The company appears capable of meeting its short-term obligations, "
            "although its liquidity cushion is more limited."
        )
    else:
        liquidity_description = "weak"
        liquidity_conclusion = (
            "The company's ability to meet short-term obligations may require "
            "additional review."
        )

    liquidity_analysis = (
        f"The company demonstrates {liquidity_description} short-term liquidity. "
        f"Its current ratio is {current_ratio:.2f}, meaning it has approximately "
        f"${current_ratio:.2f} of current assets for every $1.00 of current "
        f"liabilities. Its quick ratio is {quick_ratio:.2f}. "
        f"{liquidity_conclusion} The company earned {liquidity_score}/20 "
        f"points in the liquidity category."
        + (f" {liquidity_support_note}" if liquidity_support_note else "")
    )

    if (
        debt_to_equity <= 0.50
        and net_debt_to_ebitda <= 2.0
        and (interest_coverage is None or interest_coverage >= 5.0)
    ):
        leverage_description = "low"
        leverage_conclusion = (
            "This indicates limited net leverage and strong capacity to service "
            "existing debt obligations."
        )
    elif (
        debt_to_equity <= 1.00
        and net_debt_to_ebitda <= 3.5
        and (interest_coverage is None or interest_coverage >= 2.0)
    ):
        leverage_description = "moderate"
        leverage_conclusion = (
            "The company's debt burden appears manageable, but leverage and "
            "debt-service capacity should continue to be monitored."
        )
    else:
        leverage_description = "elevated"
        leverage_conclusion = (
            "The company's debt burden or debt-service capacity may reduce "
            "financial flexibility and increase repayment risk."
        )

    leverage_analysis = (
        f"The company has a {leverage_description} level of financial leverage. "
        f"Total debt is {total_debt_text}, net debt is {net_debt_text}, and "
        f"shareholders' equity is {equity_text}. Its debt-to-equity ratio is "
        f"{debt_to_equity_text}, gross debt-to-EBITDA is "
        f"{debt_to_ebitda_text}, and net debt-to-EBITDA is "
        f"{net_debt_to_ebitda_text}. Interest coverage is "
        f"{interest_coverage_text}, while operating cash flow equals "
        f"{operating_cash_flow_to_debt_text} of total debt. "
        f"{leverage_conclusion} Its raw leverage score was "
        f"{leverage_score}/25, contributing {weighted_leverage_score}/30 "
        f"points to the weighted base score."
    )

    if ebitda_margin >= 0.20 and net_margin >= 0.10:
        profitability_description = "strong"
        profitability_conclusion = (
            "These results indicate substantial earnings capacity and provide a "
            "strong foundation for debt repayment."
        )
    elif ebitda_margin > 0 and net_margin > 0:
        profitability_description = "positive but moderate"
        profitability_conclusion = (
            "The company is profitable, although its earnings cushion is less substantial."
        )
    else:
        profitability_description = "weak"
        profitability_conclusion = (
            "Weak or negative profitability may limit the company's ability to "
            "support future debt obligations."
        )

    profitability_analysis = (
        f"The company demonstrates {profitability_description} profitability. "
        f"For fiscal year {income_fiscal_year}, it reported revenue of "
        f"{revenue_text}, EBITDA of {ebitda_text}, and net income of "
        f"{net_income_text}. Its EBITDA margin is {ebitda_margin:.2%}, its "
        f"net margin is {net_margin:.2%}, and its return on equity is "
        f"{return_on_equity_text}. {profitability_conclusion} The company "
        f"earned {profitability_score}/20 points in the profitability category."
    )

    if operating_cash_flow > 0 and free_cash_flow > 0 and cash_conversion_ratio >= 0.80:
        cash_flow_description = "strong"
        cash_flow_conclusion = (
            "The company is generating substantial cash from operations and "
            "converting a meaningful portion of accounting earnings into cash."
        )
    elif operating_cash_flow > 0 and free_cash_flow > 0:
        cash_flow_description = "positive"
        cash_flow_conclusion = (
            "The company generates positive operating and free cash flow, though "
            "the conversion of earnings into cash is less robust."
        )
    else:
        cash_flow_description = "weak"
        cash_flow_conclusion = (
            "Weak or negative cash generation may reduce the company's ability "
            "to fund operations and repay debt internally."
        )

    cash_flow_analysis = (
        f"The company demonstrates {cash_flow_description} cash-flow performance. "
        f"Operating cash flow was {operating_cash_flow_text}, while free cash "
        f"flow was {free_cash_flow_text}. Its operating cash-flow margin was "
        f"{operating_cash_flow_margin:.2%}, and its free cash-flow margin was "
        f"{free_cash_flow_margin:.2%}. The cash-conversion ratio was "
        f"{cash_conversion_ratio:.2f}. {cash_flow_conclusion} The company "
        f"earned a raw cash-flow score of {cash_flow_score}/20, contributing "
        f"{weighted_cash_flow_score}/25 points to the weighted base score."
    )

    if beta is None:
        market_risk_description = "partially measurable"
        market_risk_conclusion = (
            "A complete market-risk assessment is limited because beta was unavailable."
        )
    elif beta <= 1.10 and annualized_volatility <= 0.30 and max_drawdown >= -0.35:
        market_risk_description = "low"
        market_risk_conclusion = (
            "The stock has demonstrated relatively stable market behavior."
        )
    elif beta <= 1.50 and annualized_volatility <= 0.50 and max_drawdown >= -0.50:
        market_risk_description = "moderate"
        market_risk_conclusion = (
            "The stock has demonstrated meaningful market fluctuations, but its "
            "risk measures remain within a moderate range."
        )
    else:
        market_risk_description = "high"
        market_risk_conclusion = (
            "The stock has experienced substantial market volatility and large "
            "declines from previous peaks."
        )

    market_risk_analysis = (
        f"The company demonstrates {market_risk_description} market risk. Over "
        f"the analyzed {years:.2f}-year period, its stock produced an annualized "
        f"return of {annualized_return:.2%}, with annualized volatility of "
        f"{annualized_volatility:.2%}. Its beta is {beta_text}, and its maximum "
        f"drawdown was {max_drawdown:.2%}. {market_risk_conclusion} Market-price "
        f"risk does not directly equal default risk, but it may reflect investor "
        f"uncertainty and sensitivity to economic or industry changes. The "
        f"company earned a raw market-risk score of {market_risk_score}/15, "
        f"contributing {weighted_market_risk_score}/5 points to the weighted "
        f"base score."
    )

    strengths: list[str] = []
    risks: list[str] = []
    if liquidity_score >= 16:
        strengths.append("strong short-term liquidity")
    if leverage_score >= 20:
        strengths.append("low financial leverage")
    if profitability_score >= 16:
        strengths.append("strong profitability")
    if cash_flow_score >= 16:
        strengths.append("strong cash generation")
    if revenue_cagr is not None and revenue_cagr >= 0.10:
        strengths.append("strong historical revenue growth")

    if market_risk_score < 8:
        risks.append("elevated stock-market risk")
    if current_ratio < 1.0:
        risks.append("limited short-term liquidity")
    if net_debt_to_ebitda > scoring_profile["debt_warning_threshold"]:
        risks.append("a high net-debt burden relative to EBITDA")
    if interest_coverage is not None and interest_coverage < 2.0:
        risks.append("weak interest coverage")
    if net_margin <= 0:
        risks.append("weak or negative net profitability")
    if free_cash_flow <= 0:
        risks.append("negative free cash flow")
    if revenue_cagr is not None and revenue_cagr < 0:
        risks.append("declining historical revenue")

    strengths_text = (
        ", ".join(strengths)
        if strengths
        else "no major strengths identified by the model"
    )
    risks_text = (
        ", ".join(risks)
        if risks
        else "no major risks identified by the model"
    )
    strengths_and_risks = (
        f"The primary strengths identified by the Srini Credit model are "
        f"{strengths_text}. The primary risks requiring consideration are "
        f"{risks_text}."
    )

    if model_suitability == "Unsupported business model":
        final_conclusion = (
            f"The standard Srini Credit framework is not designed to provide a "
            f"definitive lending conclusion for {company_name}. The displayed "
            f"numeric score is a preliminary screening result only. A specialized "
            f"credit model using industry-specific capital, reserve, regulatory, "
            f"or asset-quality measures is required before a lending decision."
        )
    elif model_suitability == "Limited suitability":
        final_conclusion = (
            f"The Srini Credit score for {company_name} should be treated as "
            f"preliminary because this business model is only partially captured "
            f"by ordinary corporate ratios. Specialized industry analysis should "
            f"be completed before relying on the lending recommendation."
        )
    elif srinicredit_score >= 80:
        final_conclusion = (
            f"{company_name} appears to be a strong lending candidate. The "
            f"company demonstrates sufficient financial capacity to support its "
            f"existing obligations based on the information analyzed. A lender "
            f"should still review loan structure, collateral, covenants, industry "
            f"conditions, management quality, and financial projections before "
            f"making a final credit decision."
        )
    elif srinicredit_score >= 70:
        final_conclusion = (
            f"{company_name} appears to be an acceptable lending candidate, "
            f"although certain financial or market risks require additional "
            f"review. A lender may consider stronger covenants, additional "
            f"collateral, or more conservative loan terms."
        )
    elif srinicredit_score >= 60:
        final_conclusion = (
            f"A loan to {company_name} should be approached cautiously. The "
            f"company demonstrates some financial strengths, but its risk profile "
            f"may justify tighter lending terms, enhanced monitoring, and "
            f"additional protection for the lender."
        )
    else:
        final_conclusion = (
            f"{company_name} appears to present elevated lending risk under the "
            f"Srini Credit model. Additional financial analysis, collateral "
            f"protection, and significant lender safeguards would be necessary "
            f"before extending credit."
        )


    score_breakdown_text = (
        f"Scoring Profile: {scoring_profile_name}\n"
        f"Model Suitability: {model_suitability}\n"
        f"Model Confidence: {confidence_level}\n"
        f"Liquidity Contribution: {weighted_liquidity_score}/20\n"
        f"Leverage Contribution: {weighted_leverage_score}/30\n"
        f"Profitability Contribution: {weighted_profitability_score}/20\n"
        f"Cash-Flow Contribution: {weighted_cash_flow_score}/25\n"
        f"Market-Risk Contribution: {weighted_market_risk_score}/5\n"
        f"Base Srini Credit Score: {base_srinicredit_score}/100\n"
        f"Historical Trend Adjustment: {trend_adjustment:+d}\n"
        f"Uncapped Score: {uncapped_srinicredit_score}/100\n"
        f"Financial Warning Score Cap: {score_cap}/100\n"
        f"Final Srini Credit Score: {srinicredit_score}/100"
    )

    disclaimer = (
        "Srini Credit is a financial screening and educational analysis tool. "
        "It is not an official credit rating, investment recommendation, or "
        "substitute for professional underwriting and due diligence."
    )

    full_memo = (
        f"\n--- SRINI CREDIT ANALYST MEMO ---\n\n"
        f"EXECUTIVE SUMMARY\n{analyst_summary}\n\n"
        f"SCORE BREAKDOWN\n{score_breakdown_text}\n\n"
        f"COMPANY OVERVIEW\n{company_overview}\n\n"
        f"MODEL SUITABILITY\n{model_suitability_analysis}\n\n"
        f"SCORING PROFILE\n{scoring_profile_analysis}\n\n"
        f"LIQUIDITY ANALYSIS\n{liquidity_analysis}\n\n"
        f"LEVERAGE ANALYSIS\n{leverage_analysis}\n\n"
        f"PROFITABILITY ANALYSIS\n{profitability_analysis}\n\n"
        f"CASH FLOW ANALYSIS\n{cash_flow_analysis}\n\n"
        f"HISTORICAL FINANCIAL TRENDS\n{historical_trends_text}\n\n"
        f"MARKET RISK ANALYSIS\n{market_risk_analysis}\n\n"
        f"KEY STRENGTHS AND RISKS\n{strengths_and_risks}\n\n"
        f"WARNING SIGNALS\n{warning_signals_text}\n\n"
        f"FINAL CREDIT CONCLUSION\n{final_conclusion}\n\n"
        f"FINAL SRINI CREDIT RESULT\n"
        f"Base Srini Credit Score: {base_srinicredit_score}/100\n"
        f"Historical Trend Adjustment: {trend_adjustment:+d}\n"
        f"Final Srini Credit Score: {srinicredit_score}/100\n"
        f"Srini Credit Tier: {credit_tier}\n"
        f"Lending Recommendation: {lending_recommendation}\n\n"
        f"DISCLAIMER\n{disclaimer}"
    )

    detailed_output = (
        f"\n{'=' * 60}\n"
        f"DETAILED COMPANY AND FINANCIAL INFORMATION\n"
        f"{'=' * 60}\n\n"
        f"--- PROFILE ---\n"
        f"Ticker: {ticker}\n"
        f"Company Name: {company_name}\n"
        f"Sector: {sector}\n"
        f"Industry: {industry}\n"
        f"Scoring Profile: {scoring_profile_name}\n"
        f"Country: {country}\n"
        f"Stock Price: {stock_price_text}\n"
        f"Market Cap: {market_cap_text}\n"
        f"Beta: {beta_text}\n"
        f"Exchange: {exchange_name}\n"
        f"CEO: {ceo}\n"
        f"Full-Time Employees: {employee_count_text}\n\n"
        f"--- INCOME STATEMENT ---\n"
        f"Fiscal Year: {income_fiscal_year}\n"
        f"Period: {income_period}\n"
        f"Statement Date: {income_date}\n"
        f"Revenue: {revenue_text}\n"
        f"EBITDA: {ebitda_text}\n"
        f"Net Income: {net_income_text}\n\n"
        f"--- BALANCE SHEET ---\n"
        f"Fiscal Year: {balance_fiscal_year}\n"
        f"Statement Date: {balance_date}\n"
        f"Cash: {cash_text}\n"
        f"Cash and Short-Term Investments: {cash_and_investments_text}\n"
        f"Current Assets: {current_assets_text}\n"
        f"Current Liabilities: {current_liabilities_text}\n"
        f"Total Assets: {total_assets_text}\n"
        f"Total Liabilities: {total_liabilities_text}\n"
        f"Total Debt: {total_debt_text}\n"
        f"Net Debt: {net_debt_text}\n"
        f"Stockholders' Equity: {equity_text}\n\n"
        f"--- CASH-FLOW STATEMENT ---\n"
        f"Fiscal Year: {cash_flow_fiscal_year}\n"
        f"Statement Date: {cash_flow_date}\n"
        f"Operating Cash Flow: {operating_cash_flow_text}\n"
        f"Capital Expenditure: {capital_expenditure_text}\n"
        f"Free Cash Flow: {free_cash_flow_text}\n\n"
        f"--- FINANCIAL RATIOS ---\n"
        f"Current Ratio: {current_ratio:.2f}\n"
        f"Quick Ratio: {quick_ratio:.2f}\n"
        f"Debt-to-Equity: {debt_to_equity_text}\n"
        f"Gross Debt-to-EBITDA: {debt_to_ebitda_text}\n"
        f"Net Debt-to-EBITDA: {net_debt_to_ebitda_text}\n"
        f"Interest Coverage: {interest_coverage_text}\n"
        f"Operating Cash Flow-to-Debt: {operating_cash_flow_to_debt_text}\n"
        f"Operating Cash Flow / Current Liabilities: "
        f"{operating_cash_flow_to_current_liabilities_text}\n"
        f"EBITDA Margin: {ebitda_margin:.2%}\n"
        f"Net Margin: {net_margin:.2%}\n"
        f"Return on Equity: {return_on_equity_text}\n"
        f"Operating Cash-Flow Margin: {operating_cash_flow_margin:.2%}\n"
        f"Free Cash-Flow Margin: {free_cash_flow_margin:.2%}\n"
        f"Cash-Conversion Ratio: {cash_conversion_ratio:.2f}\n\n"
        f"--- HISTORICAL MARKET STATISTICS ---\n"
        f"Number of Price Records: {len(historical_data)}\n"
        f"Oldest Date: {historical_data[0]['date']}\n"
        f"Newest Date: {historical_data[-1]['date']}\n"
        f"Starting Price: ${oldest_price:.2f}\n"
        f"Ending Price: ${newest_price:.2f}\n"
        f"Total Return: {total_return:.2%}\n"
        f"Years of Data: {years:.2f}\n"
        f"Annualized Return: {annualized_return:.2%}\n"
        f"Annualized Volatility: {annualized_volatility:.2%}\n"
        f"Maximum Drawdown: {max_drawdown:.2%}\n\n"
        f"--- SCORE BREAKDOWN ---\n"
        f"{score_breakdown_text}"
    )

    category_scores = [
        ("Liquidity", weighted_liquidity_score, 20),
        ("Leverage", weighted_leverage_score, 30),
        ("Profitability", weighted_profitability_score, 20),
        ("Cash Flow", weighted_cash_flow_score, 25),
        ("Market Risk", weighted_market_risk_score, 5),
    ]

    raw_category_scores = [
        ("Liquidity", liquidity_score, 20),
        ("Leverage", leverage_score, 25),
        ("Profitability", profitability_score, 20),
        ("Cash Flow", cash_flow_score, 20),
        ("Market Risk", market_risk_score, 15),
    ]

    memo_sections = [
        ("Executive Summary", analyst_summary),
        ("Company Overview", company_overview),
        ("Model Suitability", model_suitability_analysis),
        ("Scoring Profile", scoring_profile_analysis),
        ("Liquidity Analysis", liquidity_analysis),
        ("Leverage Analysis", leverage_analysis),
        ("Profitability Analysis", profitability_analysis),
        ("Cash Flow Analysis", cash_flow_analysis),
        ("Historical Financial Trends", historical_trends_text),
        ("Market Risk Analysis", market_risk_analysis),
        ("Key Strengths and Risks", strengths_and_risks),
        ("Warning Signals", warning_signals_text),
        ("Final Credit Conclusion", final_conclusion),
        ("Disclaimer", disclaimer),
    ]

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "country": country,
        "scoring_profile_key": scoring_profile_key,
        "scoring_profile_name": scoring_profile_name,
        "scoring_profile_description": scoring_profile_description,
        "model_suitability": model_suitability,
        "model_suitability_reason": model_suitability_reason,
        "confidence_level": confidence_level,
        "confidence_reason": confidence_reason,
        "model_scope_warning": model_scope_warning,
        "credit_tier": credit_tier,
        "lending_recommendation": lending_recommendation,
        "srinicredit_score": srinicredit_score,
        "uncapped_srinicredit_score": uncapped_srinicredit_score,
        "score_cap": score_cap,
        "score_cap_applied": score_cap_applied,
        "financial_warning_count": financial_warning_count,
        "market_warning_count": market_warning_count,
        "critical_warning_count": critical_warning_count,
        "major_warning_count": major_warning_count,
        "informational_warning_count": informational_warning_count,
        "critical_warning_signals": critical_warning_signals,
        "major_warning_signals": major_warning_signals,
        "informational_warning_signals": informational_warning_signals,
        "base_srinicredit_score": base_srinicredit_score,
        "trend_adjustment": trend_adjustment,
        "category_scores": category_scores,
        "raw_category_scores": raw_category_scores,
        "score_breakdown_text": score_breakdown_text,
        "memo_sections": memo_sections,
        "full_memo": full_memo,
        "detailed_output": detailed_output,
        "warning_signals": warning_signals,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "net_debt_to_ebitda_text": net_debt_to_ebitda_text,
        "interest_coverage": interest_coverage,
        "interest_coverage_text": interest_coverage_text,
        "operating_cash_flow_to_debt": operating_cash_flow_to_debt,
        "operating_cash_flow_to_debt_text": operating_cash_flow_to_debt_text,
        "operating_cash_flow_to_current_liabilities": (
            operating_cash_flow_to_current_liabilities
        ),
        "operating_cash_flow_to_current_liabilities_text": (
            operating_cash_flow_to_current_liabilities_text
        ),
        "liquidity_support_applied": liquidity_support_applied,
        "liquidity_support_note": liquidity_support_note,
        "interest_coverage_scoring_note": interest_coverage_scoring_note,
        "historical_data": historical_data,
        "raw": {
            "company": company,
            "income_statement": income_statement,
            "balance_sheet": balance_sheet,
            "cash_flow_statement": cash_flow_statement,
        },
    }


def save_text_report(
    result: dict[str, Any],
    output_directory: str | Path = ".",
    report_time: str | None = None,
) -> Path:
    """Save the full memo as a timestamped text file."""

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    if report_time is None:
        report_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    filename = (
        f"{result['ticker']}_srini_credit_memo_{report_time}.txt"
    )
    file_path = output_path / filename
    file_path.write_text(result["full_memo"], encoding="utf-8")
    return file_path


def create_credit_pdf(
    result: dict[str, Any],
    output_directory: str | Path = ".",
    report_time: str | None = None,
) -> Path:
    """Create and save a formatted Srini Credit PDF report."""

    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    if report_time is None:
        report_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    pdf_path = output_path / (
        f"{result['ticker']}_srini_credit_memo_{report_time}.pdf"
    )

    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=f"{result['ticker']} Srini Credit Report",
        author="Srini Credit",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="SriniTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        name="SriniSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4D5B69"),
        spaceAfter=18,
    )
    section_style = ParagraphStyle(
        name="SriniSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#17324D"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        name="SriniBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        spaceAfter=8,
    )
    small_style = ParagraphStyle(
        name="SriniSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#555555"),
    )
    score_style = ParagraphStyle(
        name="SriniScore",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=23,
        textColor=colors.HexColor("#17324D"),
    )
    tier_style = ParagraphStyle(
        name="SriniTier",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#17324D"),
    )
    label_style = ParagraphStyle(
        name="SriniLabel",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4D5B69"),
    )

    def safe_pdf_text(value: Any) -> str:
        return escape(str(value)).replace("\n", "<br/>")

    story: list[Any] = [
        Paragraph("SRINI CREDIT ANALYST REPORT", title_style),
        Paragraph(
            safe_pdf_text(
                f"{result['company_name']} ({result['ticker']})"
            ),
            subtitle_style,
        ),
    ]

    summary_table_data = [
        [
            Paragraph("FINAL SCORE", label_style),
            Paragraph("CREDIT TIER", label_style),
            Paragraph("RECOMMENDATION", label_style),
        ],
        [
            Paragraph(f"{result['srinicredit_score']}/100", score_style),
            Paragraph(safe_pdf_text(result["credit_tier"]), tier_style),
            Paragraph(
                safe_pdf_text(result["lending_recommendation"]),
                body_style,
            ),
        ],
    ]

    summary_table = Table(
        summary_table_data,
        colWidths=[1.45 * inch, 1.65 * inch, 3.15 * inch],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F7FA")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#17324D")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#AAB7C4")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 18)])

    story.append(Paragraph("SCORE BREAKDOWN", section_style))
    score_table_data: list[list[str]] = [
        ["Category", "Points Earned", "Maximum Points"]
    ]
    for category_name, earned_points, maximum_points in result["category_scores"]:
        score_table_data.append(
            [category_name, str(earned_points), str(maximum_points)]
        )
    score_table_data.extend(
        [
            [
                "Base Srini Credit Score",
                str(result["base_srinicredit_score"]),
                "100",
            ],
            [
                "Historical Trend Adjustment",
                f"{result['trend_adjustment']:+d}",
                "+/- 5",
            ],
            [
                "Financial Warning Score Cap",
                str(result["score_cap"]),
                "100",
            ],
            [
                "Final Srini Credit Score",
                str(result["srinicredit_score"]),
                "100",
            ],
        ]
    )

    score_table = Table(
        score_table_data,
        colWidths=[3.25 * inch, 1.45 * inch, 1.45 * inch],
        repeatRows=1,
    )
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DCE6F0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB7C4")),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([score_table, Spacer(1, 12)])

    for section_title, section_content in result["memo_sections"]:
        story.append(Paragraph(safe_pdf_text(section_title), section_style))
        story.append(Paragraph(safe_pdf_text(section_content), body_style))

    story.extend(
        [
            Spacer(1, 10),
            Paragraph(
                "Generated by Srini Credit. This report is intended for "
                "financial screening and educational purposes.",
                small_style,
            ),
        ]
    )

    def add_page_number(canvas: Any, document_object: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawRightString(
            letter[0] - 0.65 * inch,
            0.38 * inch,
            f"Srini Credit | {result['ticker']} | Page {document_object.page}",
        )
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )
    return pdf_path

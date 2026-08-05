"""Batch validation tool for the Srini Credit scoring model."""

import csv
import time

from config import API_KEY
from credit_engine import (
    FinancialDataError,
    UnsupportedTickerError,
    analyze_company,
)


TICKERS_TO_TEST = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "ORCL", "IBM",
    "WMT", "COST", "TGT", "HD", "LOW", "KO", "PEP", "PG",
    "CAT", "DE", "HON", "UPS", "LMT",
    "XOM", "CVX", "COP",
    "VZ", "T",
    "F", "GM",
]


def main() -> None:
    validation_results = []

    for ticker in TICKERS_TO_TEST:
        print(f"\nAnalyzing {ticker}...")

        try:
            result = analyze_company(ticker, API_KEY)
        except UnsupportedTickerError:
            print(f"{ticker}: Unsupported by the API or subscription.")
            continue
        except FinancialDataError as error:
            print(f"{ticker}: Financial data error — {error}")
            continue
        except Exception as error:
            print(f"{ticker}: Unexpected error — {error}")
            continue

        category_scores = {
            category_name: earned_points
            for category_name, earned_points, _maximum_points
            in result["category_scores"]
        }

        validation_results.append(
            {
                "Ticker": result["ticker"],
                "Company": result["company_name"],
                "Sector": result["sector"],
                "Industry": result["industry"],
                "Scoring Profile": result["scoring_profile_name"],
                "Liquidity": category_scores["Liquidity"],
                "Leverage": category_scores["Leverage"],
                "Profitability": category_scores["Profitability"],
                "Cash Flow": category_scores["Cash Flow"],
                "Market Risk": category_scores["Market Risk"],
                "Base Score": result["base_srinicredit_score"],
                "Trend Adjustment": result["trend_adjustment"],
                "Uncapped Score": result["uncapped_srinicredit_score"],
                "Score Cap": result["score_cap"],
                "Cap Applied": result["score_cap_applied"],
                "Final Score": result["srinicredit_score"],
                "Credit Tier": result["credit_tier"],
                "Recommendation": result["lending_recommendation"],
                "Critical Warning Count": result["critical_warning_count"],
                "Major Warning Count": result["major_warning_count"],
                "Informational Warning Count": result["informational_warning_count"],
                "Financial Warning Count": result["financial_warning_count"],
                "Market Warning Count": result["market_warning_count"],
                "Net Debt to EBITDA": result["net_debt_to_ebitda_text"],
                "Interest Coverage": result["interest_coverage_text"],
                "Operating Cash Flow to Debt": result["operating_cash_flow_to_debt_text"],
                "Warning Count": len(result["warning_signals"]),
                "Model Scope Warning": result["model_scope_warning"] or "",
                "Warnings": " | ".join(result["warning_signals"]),
            }
        )

        print(
            f"{result['ticker']}: {result['srinicredit_score']}/100 — "
            f"{result['credit_tier']}"
        )
        time.sleep(1)

    output_filename = "model_validation_results.csv"

    if not validation_results:
        print("\nNo companies were successfully analyzed.")
        return

    with open(output_filename, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=validation_results[0].keys(),
        )
        writer.writeheader()
        writer.writerows(validation_results)

    print(f"\nValidation results saved as: {output_filename}")


if __name__ == "__main__":
    main()

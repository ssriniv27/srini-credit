import csv
import time

from config import API_KEY
from credit_engine import (
    FinancialDataError,
    UnsupportedTickerError,
    analyze_company,
)

# Completely new candidate pool.
# These companies were not used in the calibration set or the first holdout test.
candidate_tickers = [
    # Technology / communication
    "META", "AVGO", "QCOM", "TXN", "ADI",
    "CRM", "INTU", "ACN", "AMD", "AMAT",

    # Consumer
    "SBUX", "YUM", "MDLZ", "KHC", "CL",
    "KMB", "ADM", "KR", "ROST", "TJX",

    # Industrials / defense / transportation
    "RTX", "NOC", "GD", "ETN", "EMR",
    "PH", "ITW", "WM", "RSG", "UNP",

    # Energy
    "EOG", "OXY", "MPC", "PSX", "SLB",
    "HAL", "KMI", "WMB",

    # Utilities
    "NEE", "DUK", "SO", "AEP", "EXC", "XEL",

    # Healthcare / pharmaceuticals
    "JNJ", "PFE", "MRK", "ABBV", "BMY", "AMGN",
]

supported = []
unsupported = []
financial_errors = []
unexpected_errors = []

for ticker in candidate_tickers:
    print(f"\nTesting {ticker}...")

    try:
        result = analyze_company(ticker, API_KEY)

        supported.append(
            {
                "Ticker": ticker,
                "Company": result.get("company_name", ""),
                "Sector": result.get("sector", ""),
                "Industry": result.get("industry", ""),
                "ModelSuitability": result.get("model_suitability", ""),
                "SriniCreditScore": result.get("srinicredit_score", ""),
                "CreditTier": result.get("credit_tier", ""),
            }
        )

        print(
            f"{ticker}: SUPPORTED — "
            f"{result.get('srinicredit_score', '')}/100"
        )

    except UnsupportedTickerError as error:
        unsupported.append(
            {
                "Ticker": ticker,
                "Reason": str(error),
            }
        )
        print(f"{ticker}: Unsupported")

    except FinancialDataError as error:
        financial_errors.append(
            {
                "Ticker": ticker,
                "Reason": str(error),
            }
        )
        print(f"{ticker}: Financial data error — {error}")

    except Exception as error:
        unexpected_errors.append(
            {
                "Ticker": ticker,
                "Reason": repr(error),
            }
        )
        print(f"{ticker}: Unexpected error — {error}")

    # Be gentle with the API.
    time.sleep(1)


with open(
    "supported_holdout_candidates.csv",
    "w",
    newline="",
    encoding="utf-8",
) as file:
    fieldnames = [
        "Ticker",
        "Company",
        "Sector",
        "Industry",
        "ModelSuitability",
        "SriniCreditScore",
        "CreditTier",
    ]

    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames,
    )

    writer.writeheader()
    writer.writerows(supported)


with open(
    "unsupported_holdout_candidates.csv",
    "w",
    newline="",
    encoding="utf-8",
) as file:
    fieldnames = ["Ticker", "Reason"]

    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames,
    )

    writer.writeheader()

    for row in unsupported:
        writer.writerow(row)

    for row in financial_errors:
        writer.writerow(row)

    for row in unexpected_errors:
        writer.writerow(row)


print("\n" + "=" * 60)
print("HOLDOUT SUPPORT TEST COMPLETE")
print("=" * 60)

print(f"Candidates tested: {len(candidate_tickers)}")
print(f"Supported: {len(supported)}")
print(f"Unsupported/API-restricted: {len(unsupported)}")
print(f"Financial-data errors: {len(financial_errors)}")
print(f"Unexpected errors: {len(unexpected_errors)}")

print("\nSupported tickers:")

if supported:
    print(", ".join(row["Ticker"] for row in supported))
else:
    print("None")

print(
    "\nSaved supported companies to: "
    "supported_holdout_candidates.csv"
)

print(
    "Saved failures to: "
    "unsupported_holdout_candidates.csv"
)
import csv
import math
import time
from pathlib import Path

from config import API_KEY
from credit_engine import (
    FinancialDataError,
    UnsupportedTickerError,
    analyze_company,
)

RATINGS_FILE = Path("external_ratings_holdout_20.csv")
MODEL_OUTPUT_FILE = Path("holdout_model_results.csv")
COMPARISON_OUTPUT_FILE = Path("holdout_external_validation_results.csv")
SUMMARY_FILE = Path("holdout_validation_summary.txt")

RATING_VALUES = {
    "AAA": 21,
    "AA+": 20,
    "AA": 19,
    "AA-": 18,
    "A+": 17,
    "A": 16,
    "A-": 15,
    "BBB+": 14,
    "BBB": 13,
    "BBB-": 12,
    "BB+": 11,
    "BB": 10,
    "BB-": 9,
    "B+": 8,
    "B": 7,
    "B-": 6,
    "CCC+": 5,
    "CCC": 4,
    "CCC-": 3,
    "CC": 2,
    "C": 1,
    "D": 0,
}


def load_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def average_ranks(values):
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)

    position = 0
    while position < len(indexed):
        tie_end = position

        while (
            tie_end + 1 < len(indexed)
            and indexed[tie_end + 1][1] == indexed[position][1]
        ):
            tie_end += 1

        average_rank = ((position + 1) + (tie_end + 1)) / 2

        for i in range(position, tie_end + 1):
            original_index = indexed[i][0]
            ranks[original_index] = average_rank

        position = tie_end + 1

    return ranks


def pearson(first_values, second_values):
    if len(first_values) != len(second_values) or len(first_values) < 2:
        return None

    first_mean = sum(first_values) / len(first_values)
    second_mean = sum(second_values) / len(second_values)

    numerator = sum(
        (a - first_mean) * (b - second_mean)
        for a, b in zip(first_values, second_values)
    )

    first_variance = sum(
        (value - first_mean) ** 2
        for value in first_values
    )

    second_variance = sum(
        (value - second_mean) ** 2
        for value in second_values
    )

    denominator = math.sqrt(first_variance * second_variance)

    if denominator == 0:
        return None

    return numerator / denominator


def spearman(first_values, second_values):
    return pearson(
        average_ranks(first_values),
        average_ranks(second_values),
    )


if not RATINGS_FILE.exists():
    raise SystemExit(
        f"{RATINGS_FILE} was not found. Put the holdout ratings CSV "
        "in the same project folder as this script."
    )

rating_rows = load_csv(RATINGS_FILE)

model_results = []

for rating_row in rating_rows:
    ticker = rating_row["Ticker"].strip().upper()
    print(f"\nAnalyzing holdout company {ticker}...")

    try:
        result = analyze_company(ticker, API_KEY)

    except UnsupportedTickerError:
        print(f"{ticker}: Unsupported by the API.")
        continue

    except FinancialDataError as error:
        print(f"{ticker}: Financial data error — {error}")
        continue

    except Exception as error:
        print(f"{ticker}: Unexpected error — {error}")
        continue

    model_results.append(
        {
            "Ticker": result["ticker"],
            "Company": result["company_name"],
            "Sector": result.get("sector", ""),
            "Industry": result.get("industry", ""),
            "ScoringProfile": result.get("scoring_profile", ""),
            "ModelSuitability": result.get("model_suitability", ""),
            "ModelConfidence": result.get("model_confidence", ""),
            "Final Score": result["srinicredit_score"],
            "Credit Tier": result["credit_tier"],
        }
    )

    print(
        f"{ticker}: {result['srinicredit_score']}/100 — "
        f"{result['credit_tier']}"
    )

    time.sleep(1)


if not model_results:
    raise SystemExit("No holdout companies were successfully analyzed.")


with MODEL_OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:
    writer = csv.DictWriter(
        f,
        fieldnames=model_results[0].keys(),
    )
    writer.writeheader()
    writer.writerows(model_results)


model_by_ticker = {
    row["Ticker"].upper(): row
    for row in model_results
}

matched = []

for rating_row in rating_rows:
    ticker = rating_row["Ticker"].strip().upper()
    external_rating = rating_row["ExternalRating"].strip().upper()

    if ticker not in model_by_ticker:
        continue

    if external_rating not in RATING_VALUES:
        print(
            f"{ticker}: External rating {external_rating!r} "
            "is not in the conversion table."
        )
        continue

    model_row = model_by_ticker[ticker]

    matched.append(
        {
            "Ticker": ticker,
            "Company": model_row["Company"],
            "Sector": model_row["Sector"],
            "Industry": model_row["Industry"],
            "ScoringProfile": model_row["ScoringProfile"],
            "ModelSuitability": model_row["ModelSuitability"],
            "ModelConfidence": model_row["ModelConfidence"],
            "SriniCreditScore": float(model_row["Final Score"]),
            "SriniCreditTier": model_row["Credit Tier"],
            "Agency": rating_row["Agency"],
            "ExternalRating": external_rating,
            "ExternalRatingValue": RATING_VALUES[external_rating],
            "Outlook": rating_row.get("Outlook", ""),
            "RatingDate": rating_row.get("RatingDate", ""),
            "Source": rating_row.get("Source", ""),
        }
    )


if len(matched) < 5:
    raise SystemExit(
        "Fewer than five holdout companies matched. "
        "The result would not be very informative."
    )


srini_scores = [row["SriniCreditScore"] for row in matched]
external_values = [row["ExternalRatingValue"] for row in matched]

overall_spearman = spearman(srini_scores, external_values)
overall_pearson = pearson(srini_scores, external_values)

srini_ranks = average_ranks(srini_scores)
external_ranks = average_ranks(external_values)

for row, srini_rank, external_rank in zip(
    matched,
    srini_ranks,
    external_ranks,
):
    row["SriniRank"] = round(srini_rank, 2)
    row["ExternalRank"] = round(external_rank, 2)
    row["AbsoluteRankDifference"] = round(
        abs(srini_rank - external_rank),
        2,
    )


matched.sort(
    key=lambda row: row["AbsoluteRankDifference"],
    reverse=True,
)


with COMPARISON_OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:
    writer = csv.DictWriter(
        f,
        fieldnames=matched[0].keys(),
    )
    writer.writeheader()
    writer.writerows(matched)


core_rows = [
    row
    for row in matched
    if row["ModelSuitability"]
    not in ("Limited suitability", "Unsupported business model")
]

core_spearman = None
core_pearson = None

if len(core_rows) >= 3:
    core_srini = [
        row["SriniCreditScore"]
        for row in core_rows
    ]
    core_external = [
        row["ExternalRatingValue"]
        for row in core_rows
    ]

    core_spearman = spearman(core_srini, core_external)
    core_pearson = pearson(core_srini, core_external)


average_rank_difference = (
    sum(row["AbsoluteRankDifference"] for row in matched)
    / len(matched)
)


summary_lines = [
    "SRINI CREDIT HOLDOUT VALIDATION",
    "=" * 50,
    f"Matched holdout companies: {len(matched)}",
    (
        f"Holdout Spearman correlation: {overall_spearman:.3f}"
        if overall_spearman is not None
        else "Holdout Spearman correlation: Unavailable"
    ),
    (
        f"Holdout Pearson correlation: {overall_pearson:.3f}"
        if overall_pearson is not None
        else "Holdout Pearson correlation: Unavailable"
    ),
    f"Average absolute rank difference: {average_rank_difference:.2f}",
    f"Core-model matched companies: {len(core_rows)}",
    (
        f"Core-model Spearman correlation: {core_spearman:.3f}"
        if core_spearman is not None
        else "Core-model Spearman correlation: Unavailable"
    ),
    (
        f"Core-model Pearson correlation: {core_pearson:.3f}"
        if core_pearson is not None
        else "Core-model Pearson correlation: Unavailable"
    ),
    "",
    "Largest holdout ranking differences:",
]

for row in matched[:5]:
    summary_lines.append(
        f"- {row['Ticker']}: Srini {row['SriniCreditScore']:.0f}, "
        f"External {row['ExternalRating']}, "
        f"rank difference {row['AbsoluteRankDifference']:.2f}"
    )


SUMMARY_FILE.write_text(
    "\n".join(summary_lines),
    encoding="utf-8",
)

print("\n")
print("\n".join(summary_lines))
print(f"\nSaved: {MODEL_OUTPUT_FILE}")
print(f"Saved: {COMPARISON_OUTPUT_FILE}")
print(f"Saved: {SUMMARY_FILE}")
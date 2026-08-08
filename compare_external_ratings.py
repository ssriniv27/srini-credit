"""Compare Srini Credit scores with an external ordinal credit-rating benchmark."""

import csv
import math
from pathlib import Path

MODEL_RESULTS_FILE = Path("model_validation_results.csv")
EXTERNAL_RATINGS_FILE = Path("external_ratings.csv")
OUTPUT_FILE = Path("external_validation_results.csv")

# Internal ordinal encoding used only for rank/correlation analysis.
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


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required file was not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def average_ranks(values: list[float]) -> list[float]:
    indexed_values = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0

    while position < len(indexed_values):
        tie_end = position
        while (
            tie_end + 1 < len(indexed_values)
            and indexed_values[tie_end + 1][1] == indexed_values[position][1]
        ):
            tie_end += 1

        average_rank = ((position + 1) + (tie_end + 1)) / 2
        for tie_position in range(position, tie_end + 1):
            original_index = indexed_values[tie_position][0]
            ranks[original_index] = average_rank
        position = tie_end + 1

    return ranks


def pearson_correlation(first_values: list[float], second_values: list[float]):
    if len(first_values) != len(second_values) or len(first_values) < 2:
        return None

    first_mean = sum(first_values) / len(first_values)
    second_mean = sum(second_values) / len(second_values)

    numerator = sum(
        (first - first_mean) * (second - second_mean)
        for first, second in zip(first_values, second_values)
    )
    first_variance = sum((value - first_mean) ** 2 for value in first_values)
    second_variance = sum((value - second_mean) ** 2 for value in second_values)
    denominator = math.sqrt(first_variance * second_variance)

    if denominator == 0:
        return None
    return numerator / denominator


def spearman_correlation(first_values: list[float], second_values: list[float]):
    return pearson_correlation(
        average_ranks(first_values),
        average_ranks(second_values),
    )


model_rows = load_csv(MODEL_RESULTS_FILE)
rating_rows = load_csv(EXTERNAL_RATINGS_FILE)
model_by_ticker = {row["Ticker"].strip().upper(): row for row in model_rows}
matched_results = []

for rating_row in rating_rows:
    ticker = rating_row["Ticker"].strip().upper()
    external_rating = rating_row["ExternalRating"].strip().upper()

    if ticker not in model_by_ticker:
        print(f"{ticker}: No Srini Credit result found.")
        continue

    if external_rating not in RATING_VALUES:
        print(f"{ticker}: Unsupported external rating {external_rating!r}.")
        continue

    model_row = model_by_ticker[ticker]
    try:
        srini_score = float(model_row["Final Score"])
    except (KeyError, TypeError, ValueError):
        print(f"{ticker}: Invalid Srini Credit score.")
        continue

    matched_results.append(
        {
            "Ticker": ticker,
            "Company": model_row.get("Company", ""),
            "Sector": model_row.get("Sector", ""),
            "Industry": model_row.get("Industry", ""),
            "ScoringProfile": model_row.get("Scoring Profile", ""),
            "ModelSuitability": model_row.get("Model Suitability", ""),
            "ModelConfidence": model_row.get("Model Confidence", ""),
            "SriniCreditScore": srini_score,
            "SriniCreditTier": model_row.get("Credit Tier", ""),
            "Agency": rating_row.get("Agency", ""),
            "ExternalRating": external_rating,
            "ExternalRatingValue": RATING_VALUES[external_rating],
            "Outlook": rating_row.get("Outlook", ""),
            "RatingDate": rating_row.get("RatingDate", ""),
            "Source": rating_row.get("Source", ""),
        }
    )

if len(matched_results) < 3:
    print("\nAt least three matched companies are needed for a useful comparison.")
    raise SystemExit(1)

srini_scores = [row["SriniCreditScore"] for row in matched_results]
external_values = [row["ExternalRatingValue"] for row in matched_results]
correlation = spearman_correlation(srini_scores, external_values)
srini_ranks = average_ranks(srini_scores)
external_ranks = average_ranks(external_values)

for row, srini_rank, external_rank in zip(
    matched_results, srini_ranks, external_ranks
):
    row["SriniRank"] = round(srini_rank, 2)
    row["ExternalRank"] = round(external_rank, 2)
    row["AbsoluteRankDifference"] = round(abs(srini_rank - external_rank), 2)

matched_results.sort(
    key=lambda row: row["AbsoluteRankDifference"],
    reverse=True,
)

with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as output_file:
    writer = csv.DictWriter(output_file, fieldnames=matched_results[0].keys())
    writer.writeheader()
    writer.writerows(matched_results)

print("\nEXTERNAL VALIDATION RESULTS")
print("=" * 50)
print(f"Matched companies: {len(matched_results)}")
if correlation is None:
    print("Spearman correlation: Unavailable")
else:
    print(f"Spearman correlation: {correlation:.3f}")
print(f"Results saved as: {OUTPUT_FILE}")

print("\nLargest ranking differences:")
for row in matched_results[:5]:
    suitability = row.get("ModelSuitability") or "Unclassified"
    print(
        f"{row['Ticker']}: Srini Credit {row['SriniCreditScore']:.0f}, "
        f"external rating {row['ExternalRating']}, rank difference "
        f"{row['AbsoluteRankDifference']:.2f}, suitability {suitability}"
    )

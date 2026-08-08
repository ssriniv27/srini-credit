import csv
import math
from collections import defaultdict
from pathlib import Path

INPUT_FILE = Path("external_validation_results.csv")
SUMMARY_FILE = Path("validation_summary.txt")
SECTOR_FILE = Path("validation_by_sector.csv")


def load_rows(path):
    if not path.exists():
        raise FileNotFoundError(
            f"{path} was not found. Run compare_external_ratings.py first."
        )

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mean(values):
    return sum(values) / len(values) if values else None


def pearson(x_values, y_values):
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None

    x_mean = mean(x_values)
    y_mean = mean(y_values)

    numerator = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(x_values, y_values)
    )

    x_variance = sum((x - x_mean) ** 2 for x in x_values)
    y_variance = sum((y - y_mean) ** 2 for y in y_values)

    denominator = math.sqrt(x_variance * y_variance)

    if denominator == 0:
        return None

    return numerator / denominator


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

        for index in range(position, tie_end + 1):
            original_index = indexed[index][0]
            ranks[original_index] = average_rank

        position = tie_end + 1

    return ranks


def spearman(x_values, y_values):
    if len(x_values) < 2:
        return None

    return pearson(
        average_ranks(x_values),
        average_ranks(y_values),
    )


rows = load_rows(INPUT_FILE)

clean_rows = []

for row in rows:
    srini_score = to_float(row.get("SriniCreditScore"))
    rating_value = to_float(row.get("ExternalRatingValue"))
    rank_difference = to_float(row.get("AbsoluteRankDifference"))

    if srini_score is None or rating_value is None:
        continue

    clean_rows.append(
        {
            **row,
            "SriniCreditScore": srini_score,
            "ExternalRatingValue": rating_value,
            "AbsoluteRankDifference": (
                rank_difference if rank_difference is not None else 0.0
            ),
        }
    )


if len(clean_rows) < 5:
    raise SystemExit(
        "At least five matched companies are recommended for this report."
    )


srini_scores = [row["SriniCreditScore"] for row in clean_rows]
rating_values = [row["ExternalRatingValue"] for row in clean_rows]
rank_differences = [row["AbsoluteRankDifference"] for row in clean_rows]

overall_spearman = spearman(srini_scores, rating_values)
overall_pearson = pearson(srini_scores, rating_values)
average_rank_difference = mean(rank_differences)

core_rows = [
    row
    for row in clean_rows
    if row.get("ModelSuitability", "")
    not in {"Limited suitability", "Unsupported business model"}
]

core_spearman = None
core_pearson = None
if len(core_rows) >= 3:
    core_srini_scores = [row["SriniCreditScore"] for row in core_rows]
    core_rating_values = [row["ExternalRatingValue"] for row in core_rows]
    core_spearman = spearman(core_srini_scores, core_rating_values)
    core_pearson = pearson(core_srini_scores, core_rating_values)


# -------------------------------------------------------------------------
# Simple linear benchmark:
# external rating value = intercept + slope * Srini score
# This is descriptive only; it is NOT used to change the Srini Credit score.
# -------------------------------------------------------------------------

x_mean = mean(srini_scores)
y_mean = mean(rating_values)

slope_numerator = sum(
    (x - x_mean) * (y - y_mean)
    for x, y in zip(srini_scores, rating_values)
)

slope_denominator = sum(
    (x - x_mean) ** 2
    for x in srini_scores
)

if slope_denominator == 0:
    slope = 0.0
else:
    slope = slope_numerator / slope_denominator

intercept = y_mean - slope * x_mean


for row in clean_rows:
    predicted_rating_value = (
        intercept + slope * row["SriniCreditScore"]
    )

    rating_residual = (
        row["ExternalRatingValue"] - predicted_rating_value
    )

    row["PredictedExternalRatingValue"] = predicted_rating_value
    row["RatingResidual"] = rating_residual


# Positive residual:
# external rating is stronger than the Srini score would imply
# -> Srini Credit may be underrating the company.
#
# Negative residual:
# external rating is weaker than the Srini score would imply
# -> Srini Credit may be overrating the company.

underrated = sorted(
    clean_rows,
    key=lambda row: row["RatingResidual"],
    reverse=True,
)

overrated = sorted(
    clean_rows,
    key=lambda row: row["RatingResidual"],
)


# -------------------------------------------------------------------------
# Sector statistics
# -------------------------------------------------------------------------

sector_groups = defaultdict(list)

for row in clean_rows:
    sector = row.get("Sector", "").strip() or "Unknown"
    sector_groups[sector].append(row)


sector_summary = []

for sector, sector_rows in sorted(sector_groups.items()):
    sector_srini = [
        row["SriniCreditScore"]
        for row in sector_rows
    ]

    sector_ratings = [
        row["ExternalRatingValue"]
        for row in sector_rows
    ]

    sector_rank_errors = [
        row["AbsoluteRankDifference"]
        for row in sector_rows
    ]

    sector_residuals = [
        row["RatingResidual"]
        for row in sector_rows
    ]

    sector_summary.append(
        {
            "Sector": sector,
            "CompanyCount": len(sector_rows),
            "AverageSriniScore": round(mean(sector_srini), 2),
            "AverageExternalRatingValue": round(mean(sector_ratings), 2),
            "AverageRankDifference": round(mean(sector_rank_errors), 2),
            "AverageRatingResidual": round(mean(sector_residuals), 3),
            "SpearmanCorrelation": (
                round(spearman(sector_srini, sector_ratings), 3)
                if len(sector_rows) >= 3
                and spearman(sector_srini, sector_ratings) is not None
                else ""
            ),
        }
    )


with SECTOR_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as output_file:
    writer = csv.DictWriter(
        output_file,
        fieldnames=[
            "Sector",
            "CompanyCount",
            "AverageSriniScore",
            "AverageExternalRatingValue",
            "AverageRankDifference",
            "AverageRatingResidual",
            "SpearmanCorrelation",
        ],
    )

    writer.writeheader()
    writer.writerows(sector_summary)


summary_lines = [
    "SRINI CREDIT EXTERNAL VALIDATION SUMMARY",
    "=" * 55,
    f"Matched companies: {len(clean_rows)}",
    (
        f"Spearman rank correlation: {overall_spearman:.3f}"
        if overall_spearman is not None
        else "Spearman rank correlation: Unavailable"
    ),
    (
        f"Pearson correlation: {overall_pearson:.3f}"
        if overall_pearson is not None
        else "Pearson correlation: Unavailable"
    ),
    f"Average absolute rank difference: {average_rank_difference:.2f}",
    (
        f"Core-model matched companies: {len(core_rows)}"
    ),
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
    "IMPORTANT INTERPRETATION",
    "The external agency rating is treated as a benchmark, not as ground truth.",
    "Core-model correlations exclude companies marked Limited suitability or",
    "Unsupported business model so specialized-model gaps do not distort the",
    "main-framework performance estimate.",
    "The linear residual analysis below is descriptive and is not used to",
    "automatically change Srini Credit scores.",
    "",
    "LARGEST POTENTIAL SRINI CREDIT UNDERRATINGS",
    "(external rating is stronger than the Srini score would imply)",
]

for row in underrated[:5]:
    summary_lines.append(
        f"- {row['Ticker']}: Srini {row['SriniCreditScore']:.0f}, "
        f"External {row['ExternalRating']}, "
        f"Residual {row['RatingResidual']:+.2f}"
    )


summary_lines.extend(
    [
        "",
        "LARGEST POTENTIAL SRINI CREDIT OVERRATINGS",
        "(external rating is weaker than the Srini score would imply)",
    ]
)

for row in overrated[:5]:
    summary_lines.append(
        f"- {row['Ticker']}: Srini {row['SriniCreditScore']:.0f}, "
        f"External {row['ExternalRating']}, "
        f"Residual {row['RatingResidual']:+.2f}"
    )


summary_lines.extend(
    [
        "",
        "SECTOR SUMMARY",
    ]
)

for sector_row in sector_summary:
    summary_lines.append(
        f"- {sector_row['Sector']}: "
        f"n={sector_row['CompanyCount']}, "
        f"avg rank difference={sector_row['AverageRankDifference']}, "
        f"avg residual={sector_row['AverageRatingResidual']}"
    )


SUMMARY_FILE.write_text(
    "\n".join(summary_lines),
    encoding="utf-8",
)


print("\n".join(summary_lines))
print(f"\nSaved: {SUMMARY_FILE}")
print(f"Saved: {SECTOR_FILE}")

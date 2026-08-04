"""Terminal interface for the Srini Credit project."""

from datetime import datetime

from config import API_KEY
from credit_engine import (
    FinancialDataError,
    UnsupportedTickerError,
    analyze_company,
    create_credit_pdf,
    save_text_report,
)


def ask_yes_or_no(prompt: str) -> bool:
    """Keep asking until the user enters yes or no."""

    while True:
        answer = input(prompt).strip().lower()

        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n"):
            return False

        print("Please enter yes or no.")


def main() -> None:
    """Run the Srini Credit terminal application."""

    while True:
        ticker = input(
            "\nEnter a stock ticker, or type EXIT to close: "
        ).strip().upper()

        if ticker == "EXIT":
            print("Srini Credit closed.")
            return

        try:
            result = analyze_company(ticker, API_KEY)
        except UnsupportedTickerError:
            print(
                f"{ticker} is unsupported by this program. "
                f"Please try another ticker."
            )
            continue
        except FinancialDataError as error:
            print(f"\nSrini Credit could not complete the analysis: {error}")
            continue

        show_details = ask_yes_or_no(
            "Would you like to see the detailed company and "
            "financial data? (yes/no): "
        )

        if show_details:
            print(result["detailed_output"])

        print(result["full_memo"])

        report_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        try:
            text_path = save_text_report(
                result,
                report_time=report_time,
            )
            pdf_path = create_credit_pdf(
                result,
                report_time=report_time,
            )
        except OSError as error:
            print(f"\nThe analysis finished, but a report could not be saved: {error}")
            return

        print(f"\nText report saved successfully as: {text_path}")
        print(f"PDF report saved successfully as: {pdf_path}")
        return


if __name__ == "__main__":
    main()
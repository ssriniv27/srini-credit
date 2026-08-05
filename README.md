# Srini Credit

Srini Credit is a Python and Streamlit corporate credit-screening application. It evaluates a public company's liquidity, leverage, profitability, cash flow, market risk, and historical financial trends, then produces a proprietary score out of 100, a credit tier, warning signals, and downloadable TXT/PDF analyst reports.

## Live Application 

Try Srini Credit Here: 

[Open the Srini Credit Dashboard](https://srinicredit.streamlit.app/)

## Disclaimer

If none of the Tickers work, this means the API has reached its daily free limit. Please wait atleast 24 hours before using again.

## Current scoring weights

- Liquidity: 20 points
- Leverage: 30 points
- Profitability: 20 points
- Cash flow: 25 points
- Market risk: 5 points
- Historical trend adjustment: -5 to +5 points

The model gives more weight to debt repayment capacity and cash generation than to stock-price volatility. It remains an educational screening model, not an official credit rating.

## Experimental industry profiles

The engine currently selects one of these provisional profiles from the FMP sector and industry labels:

- Default Corporate
- Technology
- Discount Retail
- Consumer Staples
- Telecommunications
- Integrated Energy

Each profile changes selected liquidity, leverage, profitability, and cash-flow thresholds rather than adding an arbitrary sector bonus. Financial warnings are classified as critical, major, or informational. Only critical and major financial-credit warnings can cap the score; market warnings remain informational because market risk is already included in the five-point market-risk category. The leverage analysis also uses net debt-to-EBITDA, interest coverage, and operating cash flow-to-debt. Automakers and financial institutions receive a specialized-model warning because consolidated corporate ratios can be misleading for those business models.

These profiles are experimental calibration choices and should be tested against a larger sample and external credit outcomes before being treated as predictive.

## Project files

- `credit_engine.py`: API requests, calculations, scoring, trends, memo generation, and PDF creation
- `dashboard.py`: Streamlit web application
- `main.py`: terminal application
- `validate_model.py`: batch model-validation script
- `requirements.txt`: Python packages

## Local setup

Install packages:

```bash
pip install -r requirements.txt
```

For the terminal application, copy `config.example.py` to `config.py` and add your FMP key:

```python
API_KEY = "YOUR_FMP_API_KEY"
```

For the Streamlit dashboard, create `.streamlit/secrets.toml` using the example file:

```toml
API_KEY = "YOUR_FMP_API_KEY"
```

Run the dashboard:

```bash
python -m streamlit run dashboard.py
```

Run the terminal version:

```bash
python main.py
```

Run model validation:

```bash
python validate_model.py
```

## Disclaimer

Srini Credit is a financial-screening and educational tool. It is not an official credit rating, investment recommendation, or substitute for professional underwriting and due diligence.

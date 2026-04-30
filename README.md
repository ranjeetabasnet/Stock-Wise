# StockWise 📈

> A beginner-friendly stock education web app — AI-powered news summaries, live charts, portfolio tracking, and an investing classroom, all explained in plain English.

---

## What is StockWise?

StockWise is built for people who are completely new to investing. No Wall Street jargon, no confusing dashboards — just clear explanations, live data, and an AI coach that answers your questions like a patient teacher.

### Features

| Feature | Description |
|---|---|
| **Portfolio Tracker** | Upload a CSV or JSON of your past trades and see them displayed in a clean table |
| **Watchlist** | Search and save any stock or ETF ticker; live prices update every 15 seconds |
| **Live Stock Charts** | Price + volume charts with 1D / 1W / 1M / 3M / 6M / 1Y range buttons |
| **Key Stats** | Market cap, P/E ratio, 52-week high/low, volume — with plain-English hover tooltips on every stat |
| **AI News Summary** | Gemini reads the latest headlines and writes a 3–4 paragraph beginner-friendly summary |
| **Fintech Term Highlights** | 70+ investing terms are highlighted in every AI response; hover any one to see its definition instantly |
| **Trading Story (Retrospectives)** | For every stock you've sold, shows what happened after — what you made vs what you'd have if you'd held, plus a personalised AI reflection |
| **AI Recommendation** | Gemini analyses price signals, stats, and news to give a structured educational take on a stock |
| **Investing Classroom** | Ask the AI anything, click topic cards for instant lessons, and take personalised quizzes |
| **User Accounts** | Sign up / log in to save your portfolio and watchlist permanently across sessions |

---

## Screenshots

><img width="773" height="586" alt="Screenshot 2026-04-30 at 12 55 35 AM" src="https://github.com/user-attachments/assets/a83aaf22-d398-4972-84c9-a2b0fcf55477" />
<img width="734" height="820" alt="Screenshot 2026-04-30 at 12 55 03 AM" src="https://github.com/user-attachments/assets/7378e38d-d5ff-45ff-b36b-5dc332b41485" />


---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask, Flask-Login |
| Frontend | HTML, CSS (dark theme, custom design), Vanilla JavaScript |
| Charts | Chart.js (via CDN) |
| Stock Data | [yfinance](https://github.com/ranaroussi/yfinance) |
| News | Google News RSS |
| AI | Google Gemini API (`gemini-2.5-flash`) via `google-genai` SDK |
| Auth | Flask-Login with bcrypt-style password hashing |
| Storage | JSON file (`users.json`) for accounts; Flask session for guests |

---

## Project Structure

```
stockwise/
├── app.py                   # Flask app + all routes + API logic
├── .env                     # API keys (never committed)
├── requirements.txt
├── users.json               # User accounts (auto-created on first signup)
├── templates/
│   ├── base.html            # Shared layout, navbar, footer
│   ├── index.html           # Dashboard / landing page
│   ├── stock_detail.html    # Individual stock view
│   ├── learn.html           # Investing Classroom
│   ├── login.html
│   └── signup.html
├── static/
│   ├── css/style.css        # Full dark-theme stylesheet
│   └── js/
│       ├── main.js          # Watchlist interactions
│       └── fintech.js       # Shared fintech term definitions
└── uploads/                 # Temporary storage for uploaded portfolios
```

---

## Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd "StockWise Final/Stock-Wise/stockwise"
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Create your `.env` file

Create a file called `.env` inside the `stockwise/` folder with the following:

```
GEMINI_API_KEY=your_gemini_api_key_here
FLASK_SECRET_KEY=any_random_string_here
```

**Getting a Gemini API key:**
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API key**
3. Copy it into your `.env` file

> `yfinance` is used for all stock data — no API key required.

### 4. Run the app

```bash
python3 -m flask run --port 5001
```

Then open your browser to **http://127.0.0.1:5001**

Press `Ctrl + C` to stop the server.

---

## Sample Portfolio Format

Download a sample file from the app at `/sample-portfolio`, or create your own:

**CSV format:**
```csv
Symbol,Shares,Buy Price,Sell Price,Sell Date
AAPL,15,150.00,,
VOO,5,400.00,,
NVDA,10,400.00,550.00,2024-03-01
```

**JSON format:**
```json
[
  { "Symbol": "AAPL", "Shares": 15, "Buy Price": 150.00, "Sell Price": "", "Sell Date": "" },
  { "Symbol": "VOO",  "Shares": 5,  "Buy Price": 400.00, "Sell Price": "", "Sell Date": "" },
  { "Symbol": "NVDA", "Shares": 10, "Buy Price": 400.00, "Sell Price": 550.00, "Sell Date": "2024-03-01" }
]
```

- Leave `Sell Price` and `Sell Date` blank for stocks you're still holding
- Fill them in for stocks you've already sold — this unlocks the **Trading Story** retrospective section

---

## API Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET, POST | Dashboard / landing page; handles portfolio upload |
| `/stock/<ticker>` | GET | Stock detail page |
| `/learn` | GET | Investing Classroom |
| `/learn/ask` | POST | Ask the AI a question (JSON) |
| `/learn/quiz` | POST | Generate a personalised quiz (JSON) |
| `/api/quote/<ticker>` | GET | Current price, today's change, company name |
| `/api/chart/<ticker>?range=` | GET | OHLCV chart data (1d/1w/1m/3m/6m/1y) |
| `/api/stats/<ticker>` | GET | Market cap, P/E, 52-week range, volume |
| `/api/ai_summary/<ticker>` | GET | Gemini news overview + sources |
| `/api/recommendation/<ticker>` | GET | Gemini educational stock analysis |
| `/api/retrospective/<ticker>` | POST | Gemini trade retrospective |
| `/add_watchlist` | POST | Add ticker to watchlist |
| `/remove_watchlist` | POST | Remove ticker from watchlist |
| `/sample-portfolio` | GET | Download sample CSV |
| `/signup` `/login` `/logout` | GET, POST | User auth |

---

## Notes

- **No paid APIs required.** Everything runs on free tiers — yfinance for stock data, Gemini free tier for AI.
- **No database.** User accounts are stored in `users.json`; guest data lives in the Flask session.
- **Gemini rate limits.** The free tier allows ~1,500 requests/day. If the AI coach seems slow or fails, wait a moment and refresh.
- **Not financial advice.** All AI content is for educational purposes only. Always consult a qualified financial advisor before making investment decisions.

---

## Built for beginner investors 🎓

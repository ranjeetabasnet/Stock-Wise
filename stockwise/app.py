

import os
import csv
import json
import requests
import urllib.parse
import re
from bs4 import BeautifulSoup
import yfinance as yf
import hashlib
import time
import threading
import queue
try:
    from newspaper import Article
    HAVE_NEWSPAPER = True
except Exception:
    HAVE_NEWSPAPER = False
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from google import genai as google_genai
from google.genai import types as genai_types


load_dotenv()
FINNHUB_API_KEY = None
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
_gemini_client = google_genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
GEMINI_MODEL = 'gemini-2.5-flash'

def _gemini_text(resp):
    """Safely extract text from a Gemini response (handles thinking-model empty .text)."""
    try:
        parts = resp.candidates[0].content.parts or []
        # For thinking models, filter out thought parts and return only response text
        response_parts = [p for p in parts if getattr(p, 'text', None) and not getattr(p, 'thought', False)]
        if response_parts:
            return ''.join(p.text for p in response_parts).strip()
        # Fallback: join all text parts including thoughts
        all_text = ''.join(p.text for p in parts if getattr(p, 'text', None)).strip()
        if all_text:
            return all_text
    except Exception:
        pass
    if resp and resp.text:
        return resp.text.strip()
    return None


app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev')

# Configure upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id, username, password_hash):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        u = users[user_id]
        return User(user_id, u.get('username'), u.get('password_hash'))
    return None

# Users file path
USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_users(data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def parse_portfolio(file_path, ext):
    data = []
    ext = ext.lower()
    if ext == 'csv':
        with open(file_path, encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                data.append({
                    'Symbol': row.get('Symbol', '').strip().upper(),
                    'Shares': row.get('Shares', '').strip(),
                    'Buy Price': row.get('Buy Price', '').strip(),
                    'Sell Price': row.get('Sell Price', '').strip(),
                    'Sell Date': row.get('Sell Date', '').strip(),
                })
    elif ext == 'json':
        with open(file_path, encoding='utf-8') as jsonfile:
            items = json.load(jsonfile)
            for row in items:
                data.append({
                    'Symbol': row.get('Symbol', '').strip().upper(),
                    'Shares': str(row.get('Shares', '')).strip(),
                    'Buy Price': str(row.get('Buy Price', '')).strip(),
                    'Sell Price': str(row.get('Sell Price', '')).strip(),
                    'Sell Date': str(row.get('Sell Date', '')).strip(),
                })
    return data

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'json'}

def analyze_sold_stocks(portfolio):
    """
    Analyze sold stocks from portfolio and fetch historical data for retrospectives.
    Returns list of dicts with retrospective info ready for Gemini.
    """
    sold = []
    if not portfolio:
        return sold
    
    for item in portfolio:
        sell_price_str = item.get('Sell Price', '').strip()
        sell_date_str = item.get('Sell Date', '').strip()
        
        # Only process if both sell price and sell date are provided
        if not sell_price_str or not sell_date_str:
            continue
        
        try:
            sell_price = float(sell_price_str)
            buy_price = float(item.get('Buy Price', '0').strip() or '0')
            shares = float(item.get('Shares', '1').strip() or '1')
            ticker = item.get('Symbol', '').strip().upper()
            
            if not ticker or buy_price <= 0:
                continue
            
            # Fetch current price
            try:
                current_tk = yf.Ticker(ticker)
                current_info = current_tk.info or {}
                current_price = current_info.get('regularMarketPrice') or current_info.get('currentPrice')
                
                # If not available, try fetching last close from history
                if not current_price:
                    hist = current_tk.history(period='5d')
                    if hist is not None and not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
            except Exception as e:
                print(f'Error fetching current price for {ticker}:', e)
                current_price = sell_price  # fallback
            
            if not current_price:
                continue
            
            # Fetch company name
            try:
                company_name = current_tk.info.get('shortName') or ticker
            except Exception:
                company_name = ticker
            
            # Calculate gains
            actual_gain = (sell_price - buy_price) * shares
            hypothetical_value = current_price * shares
            hypothetical_gain = (current_price - buy_price) * shares
            
            sold.append({
                'ticker': ticker,
                'company_name': company_name,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'current_price': current_price,
                'shares': shares,
                'sell_date': sell_date_str,
                'actual_value': sell_price * shares,
                'hypothetical_value': hypothetical_value,
                'actual_gain': actual_gain,
                'hypothetical_gain': hypothetical_gain
            })
        except Exception as e:
            print(f'Error analyzing sold stock {item.get("Symbol")}:', e)
            continue
    
    return sold




@app.route('/', methods=['GET', 'POST'])
def index():
    upload_error = None
    watchlist_error = None

    # If user is logged in, load their data from users.json
    if current_user.is_authenticated:
        users = load_users()
        user_data = users.get(str(current_user.id), {})
        portfolio = user_data.get('portfolio', [])
        watchlist = user_data.get('watchlist', [])
    else:
        portfolio = session.get('portfolio')
        watchlist = session.get('watchlist', [])

    # Handle portfolio upload
    if request.method == 'POST' and 'portfolio_file' in request.files:
        file = request.files['portfolio_file']
        if file.filename == '':
            upload_error = 'No selected file.'
        elif file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[1].lower()
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            try:
                parsed = parse_portfolio(file_path, ext)
                # Save to user data if logged in, otherwise session
                if current_user.is_authenticated:
                    users = load_users()
                    user_entry = users.get(str(current_user.id), {})
                    user_entry['portfolio'] = parsed
                    users[str(current_user.id)] = user_entry
                    save_users(users)
                    portfolio = parsed
                else:
                    session['portfolio'] = parsed
                    portfolio = parsed
                upload_error = None
            except Exception as e:
                upload_error = 'Could not parse file. Please check the format.'
        else:
            upload_error = 'Invalid file type. Please upload a CSV or JSON.'

    return render_template('index.html', portfolio=portfolio, upload_error=upload_error, watchlist=watchlist, watchlist_error=watchlist_error)


# Watchlist add/search/validate
@app.route('/add_watchlist', methods=['POST'])
@login_required
def add_watchlist():
    ticker = request.form.get('watchlist_ticker', '').strip().upper()
    if not ticker:
        return jsonify({'success': False, 'error': 'Please enter a ticker symbol.'}), 400
    # Validate ticker using yfinance, with a Yahoo search fallback
    try:
        info = yf.Ticker(ticker).info
        valid = bool(info and (info.get('shortName') or info.get('longName') or info.get('regularMarketPrice')))
        if not valid:
            # Fallback: use Yahoo search endpoint to try to find a matching symbol
            try:
                url = f'https://query2.finance.yahoo.com/v1/finance/search?q={ticker}'
                resp = requests.get(url, timeout=6)
                data = resp.json()
                quotes = data.get('quotes', [])
                if quotes:
                    # prefer exact symbol match
                    match_sym = None
                    for q in quotes:
                        if q.get('symbol', '').upper() == ticker:
                            match_sym = q.get('symbol')
                            break
                    if not match_sym:
                        match_sym = quotes[0].get('symbol')
                    if match_sym:
                        ticker = match_sym.upper()
                        info = yf.Ticker(ticker).info
                        valid = bool(info and (info.get('shortName') or info.get('longName') or info.get('regularMarketPrice')))
            except Exception:
                pass

        if not valid:
            return jsonify({'success': False, 'error': f"We couldn't find '{ticker}' — double-check the symbol and try again."}), 404

        description = info.get('shortName') or info.get('longName') or ''
        if current_user.is_authenticated:
            users = load_users()
            user_entry = users.get(str(current_user.id), {})
            user_watch = user_entry.get('watchlist', [])
            if any(w['symbol'].upper() == ticker for w in user_watch):
                return jsonify({'success': False, 'error': 'This ticker is already in your watchlist.'}), 400
            user_watch.append({'symbol': ticker, 'description': description})
            user_entry['watchlist'] = user_watch
            users[str(current_user.id)] = user_entry
            save_users(users)
        else:
            watchlist = session.get('watchlist', [])
            if any(w['symbol'].upper() == ticker for w in watchlist):
                return jsonify({'success': False, 'error': 'This ticker is already in your watchlist.'}), 400
            watchlist.append({'symbol': ticker, 'description': description})
            session['watchlist'] = watchlist
        print(f"Added to watchlist: {ticker} - {description}")
        return jsonify({'success': True, 'symbol': ticker, 'description': description})
    except Exception as e:
        print('Error validating ticker:', e)
        return jsonify({'success': False, 'error': 'Could not validate ticker. Please try again.'}), 500

# Remove from watchlist
@app.route('/remove_watchlist', methods=['POST'])
@login_required
def remove_watchlist():
    ticker = request.form.get('symbol', '').strip().upper()
    if current_user.is_authenticated:
        users = load_users()
        user_entry = users.get(str(current_user.id), {})
        user_watch = user_entry.get('watchlist', [])
        new_watchlist = [w for w in user_watch if w['symbol'].upper() != ticker]
        user_entry['watchlist'] = new_watchlist
        users[str(current_user.id)] = user_entry
        save_users(users)
    else:
        watchlist = session.get('watchlist', [])
        new_watchlist = [w for w in watchlist if w['symbol'].upper() != ticker]
        session['watchlist'] = new_watchlist
    return jsonify({'success': True})


# Downloadable sample CSV
@app.route('/sample-portfolio')
def sample_portfolio():
    sample_path = os.path.join(app.root_path, 'static', 'sample_portfolio.csv')
    return send_file(sample_path, as_attachment=True)


# Signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password required')
            return redirect(url_for('signup'))
        users = load_users()
        # ensure username unique
        for uid, u in users.items():
            if u.get('username') == username:
                flash('Username already taken')
                return redirect(url_for('signup'))
        # create new user id
        next_id = 1
        if users:
            existing = [int(k) for k in users.keys() if str(k).isdigit()]
            if existing:
                next_id = max(existing) + 1
        users[str(next_id)] = {
            'username': username,
            'password_hash': generate_password_hash(password),
            'portfolio': [],
            'watchlist': []
        }
        save_users(users)
        user = User(str(next_id), username, users[str(next_id)]['password_hash'])
        login_user(user)
        return redirect(url_for('index'))
    return render_template('signup.html')


# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users = load_users()
        for uid, u in users.items():
            if u.get('username') == username:
                if check_password_hash(u.get('password_hash', ''), password):
                    user = User(uid, username, u.get('password_hash'))
                    login_user(user)
                    return redirect(url_for('index'))
                else:
                    flash('Invalid username or password')
                    return redirect(url_for('login'))
        flash('Invalid username or password')
        return redirect(url_for('login'))
    return render_template('login.html')


# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/learn')
@login_required
def learn():
    if current_user.is_authenticated:
        users = load_users()
        user_data = users.get(str(current_user.id), {})
        portfolio = user_data.get('portfolio', [])
    else:
        portfolio = session.get('portfolio', [])
    return render_template('learn.html', portfolio=portfolio)


@app.route('/learn/quiz', methods=['POST'])
@login_required
def learn_quiz():
    if not _gemini_client:
        return jsonify({'error': 'AI not configured'}), 500
    data  = request.json or {}
    topic = data.get('topic', '').strip()
    if not topic:
        return jsonify({'error': 'No topic specified'}), 400
    prompt = (
        f'Create a 5-question multiple-choice quiz about "{topic}" for complete beginner investors.\n\n'
        'Return ONLY a valid JSON array with exactly 5 objects. Each object must have:\n'
        '  "question": string\n'
        '  "options": array of exactly 4 strings\n'
        '  "correct": integer 0-3 (index of the correct answer)\n'
        '  "explanation": 1-2 sentence plain-English explanation\n\n'
        'Keep it friendly and beginner-level. Return raw JSON only — no markdown fences, no other text.'
    )
    try:
        resp = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=10000)
        )
        raw = _gemini_text(resp) or ''
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw.strip())
        questions = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError('Expected list')
        return jsonify({'topic': topic, 'questions': questions[:5]})
    except Exception as e:
        print('Quiz error:', e)
        return jsonify({'error': 'Could not generate quiz. Please try again.'}), 500


@app.route('/learn/ask', methods=['POST'])
@login_required
def learn_ask():
    if not _gemini_client:
        return jsonify({'error': 'AI not configured'}), 500

    data = request.json or {}
    question = data.get('question', '').strip()
    history  = data.get('history', [])

    if not question:
        return jsonify({'error': 'Please enter a question'}), 400

    # Build multi-turn context from recent history (last 5 exchanges)
    context_parts = []
    for turn in history[-5:]:
        q = turn.get('q', '').strip()
        a = turn.get('a', '').strip()
        if q and a:
            context_parts.append(f"Student: {q}\nTeacher: {a}")
    context_parts.append(f"Student: {question}")
    context = '\n\n'.join(context_parts)

    try:
        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=context,
            config=genai_types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=10000,
                system_instruction=(
                    "You are a patient, friendly investing teacher for complete beginners. "
                    "Your student may have never invested before. Always explain concepts using "
                    "simple everyday analogies. When relevant, refer to real stock examples "
                    "(especially popular ones like Apple, Tesla, or S&P 500 index funds). "
                    "Never recommend specific stocks to buy or sell — you are an educator, not an advisor. "
                    "Keep answers under 200 words unless the user explicitly asks for more detail."
                )
            )
        )
        answer = _gemini_text(response)
        if not answer:
            return jsonify({'error': 'Could not generate an answer. Please try again.'}), 500
        return jsonify({'answer': answer})
    except Exception as e:
        print('learn_ask error:', e)
        return jsonify({'error': 'Our AI teacher is taking a short break. Try again in a moment!'}), 500


@app.route('/stock/<ticker>')
@login_required
def stock_detail(ticker):
    return render_template('stock_detail.html', ticker=ticker)


# Chart data API for Chart.js
@app.route('/api/chart/<ticker>')
def api_chart(ticker):
    # Accept range param: 1d,1w,1m,3m,6m,1y
    r = request.args.get('range', '6m')
    # Map to yfinance period and interval
    period_interval = {
        '1d': ('1d', '5m'),
        '1w': ('7d', '30m'),
        '1m': ('1mo', '1d'),
        '3m': ('3mo', '1d'),
        '6m': ('6mo', '1d'),
        '1y': ('1y', '1d')
    }
    period, interval = period_interval.get(r, ('6mo', '1d'))
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period, interval=interval, auto_adjust=False)
        if hist is None or hist.empty:
            return jsonify({'error': 'No data found for ticker'}), 404
        # Build arrays
        # Return ISO dates (strings) for client-side formatting
        dates = [d.strftime('%Y-%m-%d %H:%M:%S') if hasattr(d, 'hour') else d.strftime('%Y-%m-%d') for d in hist.index]
        closes = [round(float(v), 2) if v is not None else None for v in hist['Close'].tolist()]
        opens = [round(float(v), 2) if v is not None else None for v in hist['Open'].tolist()]
        highs = [round(float(v), 2) if v is not None else None for v in hist['High'].tolist()]
        lows = [round(float(v), 2) if v is not None else None for v in hist['Low'].tolist()]
        volumes = [int(v) if v is not None else None for v in hist['Volume'].tolist()]
        return jsonify({'ticker': ticker.upper(), 'range': r, 'period': period, 'interval': interval, 'dates': dates, 'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes})
    except Exception as e:
        print('Chart API error:', e)
        return jsonify({'error': 'Error fetching data'}), 500


@app.route('/api/stats/<ticker>')
def api_stats(ticker):
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        info = getattr(tk, 'info', {}) or {}
        price = info.get('regularMarketPrice') or info.get('previousClose') or None
        market_cap = info.get('marketCap') or None
        pe = info.get('trailingPE') or info.get('forwardPE') or None
        vol = info.get('volume') or info.get('averageVolume') or None
        high52 = info.get('fiftyTwoWeekHigh') or info.get('fiftyTwoWeekHigh') or None
        low52 = info.get('fiftyTwoWeekLow') or info.get('fiftyTwoWeekLow') or None
        # If 52-week not available, compute from history
        try:
            if not high52 or not low52:
                hist = tk.history(period='1y')
                if hist is not None and not hist.empty:
                    high52 = high52 or float(hist['High'].max())
                    low52 = low52 or float(hist['Low'].min())
        except Exception:
            pass

        return jsonify({
            'ticker': ticker.upper(),
            'price': price,
            'marketCap': market_cap,
            'pe': pe,
            'volume': vol,
            '52WeekHigh': high52,
            '52WeekLow': low52
        })
    except Exception as e:
        print('Stats API error:', e)
        return jsonify({'error': 'Error fetching stats'}), 500


@app.route('/api/quote/<ticker>')
def api_quote(ticker):
    try:
        tk = yf.Ticker(ticker)
        info = getattr(tk, 'info', {}) or {}
        price = (info.get('regularMarketPrice') or
                 info.get('currentPrice') or
                 info.get('previousClose'))
        prev_close = (info.get('previousClose') or
                      info.get('regularMarketPreviousClose'))
        change = info.get('regularMarketChange')
        change_pct = info.get('regularMarketChangePercent')
        company_name = info.get('shortName') or info.get('longName') or ticker

        if price and prev_close:
            if change is None:
                change = round(float(price) - float(prev_close), 4)
            if change_pct is None:
                change_pct = round((float(price) - float(prev_close)) / float(prev_close) * 100, 4)

        return jsonify({
            'ticker': ticker.upper(),
            'company_name': company_name,
            'price': price,
            'previous_close': prev_close,
            'change': change,
            'change_pct': change_pct
        })
    except Exception as e:
        print('Quote API error:', e)
        return jsonify({'error': 'Could not fetch quote data'}), 500


def fetch_article_text(url, max_chars=3000):
    """Attempt to fetch an article URL and heuristically extract main text."""
    try:
        # Prefer using newspaper3k when available for better extraction
        if HAVE_NEWSPAPER:
            try:
                art = Article(url)
                art.download()
                art.parse()
                text = art.text or ''
                text = re.sub(r'\s+', ' ', text).strip()
                if text:
                    if len(text) > max_chars:
                        return text[:max_chars].rsplit(' ', 1)[0] + '...'
                    return text
            except Exception:
                pass
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return ''
        soup = BeautifulSoup(r.text, 'html.parser')
        # Prefer <article> tag
        article = soup.find('article')
        text = ''
        if article:
            ps = article.find_all('p')
            text = ' '.join(p.get_text(separator=' ', strip=True) for p in ps)
        else:
            # fallback: collect all <p> and choose the largest contiguous block
            ps = [p.get_text(separator=' ', strip=True) for p in soup.find_all('p')]
            if not ps:
                return ''
            best = ''
            for i in range(len(ps)):
                for j in range(i, min(i+8, len(ps))):
                    cand = ' '.join(ps[i:j+1])
                    if len(cand) > len(best):
                        best = cand
            text = best or ' '.join(ps)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_chars:
            return text[:max_chars].rsplit(' ', 1)[0] + '...'
        return text
    except Exception as e:
        print('fetch_article_text error', e)
        return ''

# --- Summarization cache + rate limiter + background refresher ---
_summary_cache = {}  # key -> (summary, ts)
_cache_lock = threading.Lock()
_CACHE_TTL = 60 * 60 * 24  # 24h

# Simple token-bucket rate limiter for outbound Gemini calls
class RateLimiter:
    def __init__(self, rate_per_minute=30):
        self.capacity = rate_per_minute
        self.tokens = rate_per_minute
        self.fill_interval = 60.0 / rate_per_minute
        self.lock = threading.Lock()
        self.last = time.time()

    def consume(self, amount=1):
        with self.lock:
            now = time.time()
            elapsed = now - self.last
            # refill tokens
            refill = int(elapsed / self.fill_interval)
            if refill > 0:
                self.tokens = min(self.capacity, self.tokens + refill)
                self.last = now
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

_rate_limiter = RateLimiter(rate_per_minute=int(os.environ.get('GEMINI_RATE_PER_MIN', 20)))

# Background queue to refresh summaries when rate-limited
_bg_queue = queue.Queue()

def _bg_worker():
    while True:
        item = _bg_queue.get()
        if item is None:
            break
        key, text, length = item
        try:
            s = _summarize_via_gemini(text, length)
            if s:
                with _cache_lock:
                    _summary_cache[key] = (s, time.time())
        except Exception as e:
            print('bg worker error', e)
        _bg_queue.task_done()

threading.Thread(target=_bg_worker, daemon=True).start()

def _cache_get(key):
    with _cache_lock:
        item = _summary_cache.get(key)
        if not item:
            return None
        summary, ts = item
        if time.time() - ts > _CACHE_TTL:
            del _summary_cache[key]
            return None
        return summary

def _cache_set(key, summary):
    with _cache_lock:
        _summary_cache[key] = (summary, time.time())

def _summarize_via_gemini(text, length):
    """Summarize text using Gemini API with beginner-friendly language."""
    if not _gemini_client:
        return None
    try:
        prompt = (
            "You are a friendly financial coach explaining news to complete beginners. "
            "Summarize this news article in plain English without jargon:\n\n"
            f"{text}\n\nKeep it 2-3 sentences and encouraging."
        )
        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=10000
            )
        )
        return _gemini_text(response)
    except Exception as e:
        print('Gemini summarize error:', e)
    return None


@app.route('/api/news/<ticker>')
def api_news(ticker):
    """Fetch news with Gemini-powered summary and company name."""
    try:
        # Get company name
        company_name = ticker
        try:
            t = yf.Ticker(ticker)
            company_name = t.info.get('shortName') or ticker
        except Exception:
            pass

        # Fetch Google News RSS
        query = f"{company_name} {ticker} stock"
        rss_url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(query) + '&hl=en-US&gl=US&ceid=US:en'
        hdr = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(rss_url, headers=hdr, timeout=8)
        items = []
        
        if resp.status_code == 200:
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.content)
                for itm in root.findall('.//item')[:10]:
                    title = itm.findtext('title')
                    link = itm.findtext('link')
                    source = itm.findtext('source') or ''
                    if (not source) and title and ' - ' in title:
                        parts = title.rsplit(' - ', 1)
                        title = parts[0].strip()
                        source = parts[1].strip()
                    source = source.strip() if source else ''
                    
                    # Mark trusted publishers
                    trusted_publishers = [
                        'reuters', 'bloomberg', 'wsj', 'wall street journal', 'cnbc', 'financial times',
                        'ft', 'marketwatch', 'barron', 'barron\'s', 'nytimes', 'the new york times', 'seeking alpha'
                    ]
                    src_l = (source or '').lower()
                    trusted = any(p in src_l for p in trusted_publishers)
                    
                    # Fetch article content for better summarization
                    content = ''
                    if link:
                        content = fetch_article_text(link, max_chars=3000)
                    
                    items.append({
                        'title': title,
                        'link': link,
                        'publisher': source,
                        'content': content,
                        'trusted': trusted
                    })
            except Exception as e:
                print('RSS parse error', e)
        
        return jsonify({'ticker': ticker.upper(), 'company_name': company_name, 'articles': items})
    except Exception as e:
        print('news fetch error', e)
        return jsonify({'ticker': ticker.upper(), 'company_name': '', 'articles': []})


@app.route('/api/ai_summary/<ticker>')
def api_ai_summary(ticker):
    """Generate a single beginner-friendly Gemini overview of all recent news (Phase 4)."""
    if not GEMINI_API_KEY:
        return jsonify({'error': 'AI features not configured'}), 500

    try:
        company_name = ticker
        try:
            t = yf.Ticker(ticker)
            company_name = t.info.get('shortName') or ticker
        except Exception:
            pass

        # Fetch news headlines from Google News RSS
        query = f"{company_name} {ticker} stock"
        rss_url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(query) + '&hl=en-US&gl=US&ceid=US:en'
        hdr = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(rss_url, headers=hdr, timeout=8)

        articles = []
        headline_lines = []

        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            for itm in root.findall('.//item')[:10]:
                title = itm.findtext('title') or ''
                link = itm.findtext('link') or ''
                source = itm.findtext('source') or ''
                desc = re.sub(r'<[^>]+>', '', itm.findtext('description') or '').strip()

                if title and ' - ' in title and not source:
                    parts = title.rsplit(' - ', 1)
                    title = parts[0].strip()
                    source = parts[1].strip()

                if title:
                    line = f"- {title}"
                    if desc:
                        line += f": {desc[:150]}"
                    headline_lines.append(line)
                    articles.append({'title': title, 'link': link, 'publisher': source.strip()})

        if not headline_lines:
            return jsonify({'error': 'No news articles found to summarize'}), 404

        headlines_text = '\n'.join(headline_lines)
        prompt = (
            f"Here are recent news headlines about {ticker} ({company_name}):\n"
            f"{headlines_text}\n\n"
            "Please write a 3-4 paragraph beginner-friendly summary of what's been happening "
            "with this company. Highlight any important trends. At the end, include a "
            "'Key Terms Explained' section with bullet points defining any financial terms "
            "you used, in the simplest possible language."
        )

        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=10000,
                system_instruction=(
                    "You are a friendly financial coach who explains stock news to complete beginners. "
                    "Use simple, encouraging language. Never use jargon without explaining it. "
                    "Keep explanations short and reassuring. Always present both the positive and "
                    "negative sides of any news so the user gets a balanced view."
                )
            )
        )

        summary = _gemini_text(response)
        if not summary:
            return jsonify({'error': 'Could not generate summary'}), 500

        return jsonify({
            'ticker': ticker.upper(),
            'company_name': company_name,
            'summary': summary,
            'articles': articles
        })

    except Exception as e:
        print('AI summary error:', e)
        return jsonify({'error': 'Could not generate AI summary. Please try again.'}), 500


@app.route('/api/summarize', methods=['POST'])
def api_summarize():
    payload = request.json or {}
    text = payload.get('text', '')
    length = payload.get('length', 200)
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    # Use cache first
    key = hashlib.sha256(text.encode('utf-8')).hexdigest()
    cached = _cache_get(key)
    if cached:
        return jsonify({'summary': cached, 'cached': True})

    # If rate limiter allows, call Gemini synchronously
    if _rate_limiter.consume():
        out = _summarize_via_gemini(text, length)
        if out:
            _cache_set(key, out)
            return jsonify({'summary': out, 'cached': False})
        # fallthrough to heuristic

    # If we couldn't call Gemini due to rate limiting, enqueue a background refresh
    try:
        _bg_queue.put_nowait((key, text, length))
    except Exception:
        pass

    # Final fallback: simple heuristic summarizer (first 2 sentences or trimmed)
    try:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        summary = ' '.join(sentences[:2])
        if len(summary) > length:
            summary = summary[:length].rsplit(' ', 1)[0] + '...'
        _cache_set(key, summary)
        return jsonify({'summary': summary, 'cached': False, 'note': 'fallback'})
    except Exception as e:
        print('Fallback summarizer error:', e)
        return jsonify({'summary': text[:length]})

def _fetch_news_headlines(ticker, company_name, max_items=8):
    """Fetch recent Google News headlines for a ticker. Returns list of title strings."""
    try:
        query = f"{company_name} {ticker} stock"
        rss_url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(query) + '&hl=en-US&gl=US&ceid=US:en'
        resp = requests.get(rss_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=7)
        if resp.status_code != 200:
            return []
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        headlines = []
        for itm in root.findall('.//item')[:max_items]:
            title = itm.findtext('title') or ''
            if ' - ' in title:
                title = title.rsplit(' - ', 1)[0].strip()
            if title:
                headlines.append(title)
        return headlines
    except Exception as e:
        print('fetch_news_headlines error:', e)
        return []


@app.route('/api/retrospective/<ticker>', methods=['POST'])
def api_retrospective(ticker):
    """Generate a detailed, news-aware Gemini retrospective for a sold stock."""
    if not _gemini_client:
        return jsonify({'error': 'Gemini API not configured'}), 500

    data = request.json or {}
    company_name = data.get('company_name', ticker)
    buy_price    = float(data.get('buy_price', 0))
    sell_price   = float(data.get('sell_price', 0))
    current_price= float(data.get('current_price', 0))
    shares       = float(data.get('shares', 1))
    sell_date    = data.get('sell_date', 'the sell date')

    try:
        actual_value      = sell_price * shares
        hypothetical_value= current_price * shares
        actual_gain       = (sell_price - buy_price) * shares
        hypothetical_gain = (current_price - buy_price) * shares
        sell_pct          = ((sell_price - buy_price) / buy_price * 100) if buy_price else 0
        post_pct          = ((current_price - sell_price) / sell_price * 100) if sell_price else 0

        # Fetch live stats for context
        stats_ctx = ''
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            pe      = info.get('trailingPE') or info.get('forwardPE')
            high52  = info.get('fiftyTwoWeekHigh')
            low52   = info.get('fiftyTwoWeekLow')
            mktcap  = info.get('marketCap')
            sector  = info.get('sector') or ''
            parts = []
            if pe:      parts.append(f"P/E ratio: {pe:.1f}")
            if high52:  parts.append(f"52-week high: ${high52:.2f}")
            if low52:   parts.append(f"52-week low: ${low52:.2f}")
            if mktcap:
                mc = f"${mktcap/1e12:.2f}T" if mktcap >= 1e12 else f"${mktcap/1e9:.2f}B"
                parts.append(f"Market cap: {mc}")
            if sector:  parts.append(f"Sector: {sector}")
            if parts:
                stats_ctx = '\n\nCurrent stock stats:\n' + '\n'.join(f'- {p}' for p in parts)
        except Exception:
            pass

        # Fetch current news headlines
        headlines = _fetch_news_headlines(ticker, company_name, max_items=8)
        news_ctx = ''
        if headlines:
            news_ctx = '\n\nRecent news headlines about this stock:\n' + '\n'.join(f'- {h}' for h in headlines)

        direction = 'risen' if current_price > sell_price else 'fallen'
        outcome   = 'missed out on additional gains' if hypothetical_gain > actual_gain else 'avoided further losses'

        prompt = (
            f"A beginner investor bought {shares:.0f} shares of {ticker} ({company_name}) at ${buy_price:.2f} each. "
            f"They sold on {sell_date} at ${sell_price:.2f}, "
            f"{'making' if actual_gain >= 0 else 'losing'} ${abs(actual_gain):.2f} "
            f"({sell_pct:+.1f}% from their buy price).\n\n"
            f"Since they sold, the stock has {direction} from ${sell_price:.2f} to ${current_price:.2f} "
            f"({post_pct:+.1f}%), meaning they {outcome}. "
            f"If they had held, their position would now be worth ${hypothetical_value:.2f} instead of ${actual_value:.2f}."
            f"{stats_ctx}"
            f"{news_ctx}\n\n"
            "Write a detailed, 3-paragraph educational retrospective for this beginner investor:\n\n"
            "**Paragraph 1 — Validate their decision:** Warmly acknowledge why selling was a reasonable choice at the time. "
            "Be specific about what a rational seller might have been thinking.\n\n"
            "**Paragraph 2 — What the data was signalling:** Using the stats and news context above, identify 2-3 concrete, "
            "specific signals that were present around the time of the sale — things like P/E ratio relative to sector norms, "
            "price proximity to 52-week highs/lows, news sentiment, sector headwinds or tailwinds, earnings trends, or "
            "macro factors (interest rates, inflation, etc.). Be specific and educational, not vague.\n\n"
            "**Paragraph 3 — Actionable lesson:** Give 2-3 practical, specific things this investor can look at next time "
            "before deciding to sell — for example: 'Check whether the P/E is above the sector average before selling a "
            "growing company' or 'Look at the 52-week range to see if you are selling near the bottom'. "
            "Make these lessons concrete and memorable.\n\n"
            "Tone: warm, supportive mentor — never critical or harsh. Use plain English. "
            "Acknowledge that even professional investors make timing mistakes."
        )

        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.35,
                max_output_tokens=10000,
                system_instruction=(
                    "You are a supportive investing mentor helping a complete beginner learn from their trading history. "
                    "Be specific, educational, and encouraging. Never make the user feel bad about their decisions."
                )
            )
        )
        retrospective = _gemini_text(response) or "Unable to generate reflection."

        return jsonify({
            'ticker': ticker,
            'retrospective': retrospective,
            'actual_gain': actual_gain,
            'hypothetical_gain': hypothetical_gain,
            'did_better': actual_gain >= hypothetical_gain
        })
    except Exception as e:
        print('Retrospective generation error:', e)
        return jsonify({'error': 'Could not generate retrospective'}), 500


@app.route('/api/recommendation/<ticker>')
def api_recommendation(ticker):
    """Generate a buy/sell/hold recommendation based on stats + news analysis."""
    if not _gemini_client:
        return jsonify({'error': 'Gemini API not configured'}), 500
    try:
        # Gather stats
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        company_name = info.get('shortName') or info.get('longName') or ticker
        price    = info.get('regularMarketPrice') or info.get('currentPrice')
        prev     = info.get('previousClose')
        pe       = info.get('trailingPE') or info.get('forwardPE')
        high52   = info.get('fiftyTwoWeekHigh')
        low52    = info.get('fiftyTwoWeekLow')
        mktcap   = info.get('marketCap')
        sector   = info.get('sector') or 'Unknown'
        beta     = info.get('beta')
        div_yield= info.get('dividendYield')
        analyst  = info.get('recommendationKey') or ''  # e.g. 'buy', 'hold'
        target   = info.get('targetMeanPrice')

        chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None

        # 52-week position
        position_pct = None
        if high52 and low52 and price:
            position_pct = round((price - low52) / (high52 - low52) * 100, 1)

        stats_lines = [f"- Current price: ${price:.2f}" if price else ""]
        if chg_pct is not None: stats_lines.append(f"- Today's change: {chg_pct:+.2f}%")
        if pe:           stats_lines.append(f"- P/E ratio: {pe:.1f}")
        if high52:       stats_lines.append(f"- 52-week high: ${high52:.2f}")
        if low52:        stats_lines.append(f"- 52-week low: ${low52:.2f}")
        if position_pct is not None:
            stats_lines.append(f"- Current price is at {position_pct:.0f}% of its 52-week range (0%=low, 100%=high)")
        if mktcap:
            mc = f"${mktcap/1e12:.2f}T" if mktcap >= 1e12 else f"${mktcap/1e9:.2f}B"
            stats_lines.append(f"- Market cap: {mc}")
        if sector:       stats_lines.append(f"- Sector: {sector}")
        if beta:         stats_lines.append(f"- Beta (volatility vs market): {beta:.2f}")
        if div_yield:    stats_lines.append(f"- Dividend yield: {div_yield*100:.2f}%")
        if analyst:      stats_lines.append(f"- Analyst consensus: {analyst.replace('_',' ').title()}")
        if target:       stats_lines.append(f"- Analyst price target: ${target:.2f}")
        stats_text = '\n'.join(l for l in stats_lines if l)

        # Fetch news
        headlines = _fetch_news_headlines(ticker, company_name, max_items=8)
        news_text = ''
        if headlines:
            news_text = '\n\nRecent news headlines:\n' + '\n'.join(f'- {h}' for h in headlines)

        prompt = (
            f"You are analysing {ticker} ({company_name}) for a complete beginner investor.\n\n"
            f"Stock data:\n{stats_text}"
            f"{news_text}\n\n"
            "Based on ALL of the above — stock stats, market position, and recent news — provide:\n\n"
            "1. **Verdict**: One word — BUY, SELL, or HOLD\n"
            "2. **Confidence**: Low, Moderate, or High\n"
            "3. **Key reasons** (3-4 bullet points, plain English, specific to this stock's actual data)\n"
            "4. **Main risks** (2-3 bullet points — things that could go wrong)\n"
            "5. **One sentence** reminding the user this is educational analysis, not personalised financial advice\n\n"
            "Be honest and balanced. Do not be overly optimistic. Reference the actual numbers provided. "
            "Use simple language a first-time investor will understand."
        )

        response = _gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=10000,
                system_instruction=(
                    "You are an objective financial educator providing data-driven stock analysis for beginners. "
                    "Be specific, balanced, and honest. Always reference the actual data provided."
                )
            )
        )
        analysis = _gemini_text(response)
        if not analysis:
            return jsonify({'error': 'Could not generate analysis'}), 500

        # Extract top-level verdict for the badge
        verdict = 'HOLD'
        for word in ['BUY', 'SELL', 'HOLD']:
            if word in analysis.upper()[:120]:
                verdict = word
                break

        return jsonify({
            'ticker': ticker.upper(),
            'company_name': company_name,
            'verdict': verdict,
            'analysis': analysis
        })
    except Exception as e:
        print('Recommendation error:', e)
        return jsonify({'error': 'Could not generate recommendation'}), 500


# AJAX endpoint for ticker search suggestions using Yahoo's public search
@app.route('/search_tickers')
def search_tickers():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    url = f'https://query2.finance.yahoo.com/v1/finance/search?q={query}'
    try:
        resp = requests.get(url, timeout=6)
        data = resp.json()
        quotes = data.get('quotes', [])
        suggestions = []
        for item in quotes[:10]:
            sym = item.get('symbol')
            name = item.get('shortname') or item.get('longname') or ''
            if sym:
                suggestions.append({'symbol': sym, 'description': name})
        return jsonify(suggestions)
    except Exception:
        return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', os.environ.get('FLASK_RUN_PORT', 5001)))
    app.run(debug=True, host='127.0.0.1', port=port)

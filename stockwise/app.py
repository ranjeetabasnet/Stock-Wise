

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
import google.generativeai as genai


load_dotenv()
# yfinance does not require API keys
FINNHUB_API_KEY = None
# Initialize Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


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
def add_watchlist():
    # require login
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Please log in to add to your watchlist.'}), 401

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

@app.route('/stock/<ticker>')
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
    if not GEMINI_API_KEY:
        return None
    try:
        prompt = f"You are a friendly financial coach explaining news to complete beginners. Summarize this news article in plain English without jargon:\n\n{text}\n\nKeep it 2-3 sentences and encouraging."
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=min(512, int(length / 2) + 100)
            )
        )
        if response and response.text:
            return response.text.strip()
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

@app.route('/api/retrospective/<ticker>', methods=['POST'])
def api_retrospective(ticker):
    """Generate a Gemini-powered retrospective for a sold stock."""
    if not GEMINI_API_KEY:
        return jsonify({'error': 'Gemini API not configured'}), 500
    
    data = request.json or {}
    company_name = data.get('company_name', ticker)
    buy_price = data.get('buy_price', 0)
    sell_price = data.get('sell_price', 0)
    current_price = data.get('current_price', 0)
    shares = data.get('shares', 1)
    
    try:
        actual_value = sell_price * shares
        hypothetical_value = current_price * shares
        actual_gain = (sell_price - buy_price) * shares
        hypothetical_gain = (current_price - buy_price) * shares
        
        prompt = f"""A beginner investor bought {shares} shares of {ticker} ({company_name}) at ${buy_price} each. 
They sold at ${sell_price} on their sell date, making ${actual_gain:.2f} ({((sell_price - buy_price) / buy_price * 100):.1f}%).

Since they sold, the stock price has gone from ${sell_price} to ${current_price}, which means if they had held, 
their position would now be worth ${hypothetical_value:.2f} instead of ${actual_value:.2f}.

Write a short, encouraging 2-paragraph reflection that:
1. Validates their decision to sell (they had a reason and that's okay)
2. Explains what signs an app like StockWise could have shown them that might have helped them decide

Be supportive and educational, not critical. Focus on learning, not regret."""
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=400
            )
        )
        
        retrospective = response.text.strip() if response and response.text else "Unable to generate reflection."
        
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

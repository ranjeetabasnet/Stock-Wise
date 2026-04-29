

import os
import csv
import json
import requests
import yfinance as yf
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user


load_dotenv()
# yfinance does not require API keys
FINNHUB_API_KEY = None


app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev')

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

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
        json.dump(data, f, indent=2)


class User(UserMixin):
    def __init__(self, id_, username, password_hash):
        self.id = id_
        self.username = username
        self.password_hash = password_hash

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    for uid, u in users.items():
        if str(uid) == str(user_id):
            return User(uid, u['username'], u['password_hash'])
    return None

# Allowed upload extensions
ALLOWED_EXTENSIONS = {'csv', 'json'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_portfolio(file_path, ext):
    data = []
    if ext == 'csv':
        with open(file_path, newline='', encoding='utf-8') as csvfile:
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

@app.route('/learn')
def learn():
    return render_template('learn.html')


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
    app.run(debug=True)



import os
import csv
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv


load_dotenv()
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')


app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev')

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
    portfolio = session.get('portfolio')
    upload_error = None
    watchlist = session.get('watchlist', [])
    watchlist_error = None

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
    ticker = request.form.get('watchlist_ticker', '').strip().upper()
    if not ticker:
        return jsonify({'success': False, 'error': 'Please enter a ticker symbol.'}), 400
    # Validate ticker with Finnhub
    url = f'https://finnhub.io/api/v1/search?q={ticker}&token={FINNHUB_API_KEY}'
    try:
        resp = requests.get(url, timeout=6)
        data = resp.json()
        results = data.get('result', [])
        if not results:
            return jsonify({'success': False, 'error': f"We couldn't find '{ticker}' — double-check the symbol and try again."}), 404
        # Accept if any result symbol matches input (case-insensitive)
        match = None
        for item in results:
            if item['symbol'].upper() == ticker:
                match = item
                break
        # If not exact, accept if input is substring of any symbol or description
        if not match:
            for item in results:
                if ticker in item['symbol'].upper() or ticker in item.get('description', '').upper():
                    match = item
                    break
        # If still not found, accept first result
        if not match:
            match = results[0]
        # Store in session
        watchlist = session.get('watchlist', [])
        # Prevent duplicates
        if any(w['symbol'].upper() == match['symbol'].upper() for w in watchlist):
            return jsonify({'success': False, 'error': 'This ticker is already in your watchlist.'}), 400
        watchlist.append({'symbol': match['symbol'].upper(), 'description': match.get('description', '')})
        session['watchlist'] = watchlist
        return jsonify({'success': True, 'symbol': match['symbol'].upper(), 'description': match.get('description', '')})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Could not validate ticker. Please try again.'}), 500

# Remove from watchlist
@app.route('/remove_watchlist', methods=['POST'])
def remove_watchlist():
    ticker = request.form.get('symbol', '').strip().upper()
    watchlist = session.get('watchlist', [])
    new_watchlist = [w for w in watchlist if w['symbol'].upper() != ticker]
    session['watchlist'] = new_watchlist
    return jsonify({'success': True})


# Downloadable sample CSV
@app.route('/sample-portfolio')
def sample_portfolio():
    sample_path = os.path.join(app.root_path, 'static', 'sample_portfolio.csv')
    return send_file(sample_path, as_attachment=True)

@app.route('/stock/<ticker>')
def stock_detail(ticker):
    return render_template('stock_detail.html', ticker=ticker)

@app.route('/learn')
def learn():
    return render_template('learn.html')

if __name__ == '__main__':
    app.run(debug=True)

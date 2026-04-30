// Shared fintech term definitions + first-occurrence highlighting
const fintechTerms = {
    'stock':            'A tiny piece of ownership in a company. Own a stock = own a slice of that business.',
    'share':            'One unit of ownership in a company — same thing as a stock.',
    'equity':           'The ownership stake in a company. Stocks and equity mean the same thing.',
    'bond':             'A loan you give to a company or government that pays you back with interest over time.',
    'etf':              'A bundle of many stocks sold as one. Cheap, easy way to invest in many companies at once.',
    'index fund':       'A fund that copies a market index like the S&P 500 automatically — low cost, low effort.',
    'mutual fund':      'A pooled fund managed by a professional who picks stocks for you.',
    'bull market':      'When stock prices are rising and investors are optimistic — a good time for stocks.',
    'bear market':      'When stock prices are falling 20%+ and investors are worried — a tough market.',
    'bull':             'An investor who expects prices to rise. Bulls are optimistic.',
    'bear':             'An investor who expects prices to fall. Bears are pessimistic.',
    'correction':       'A market drop of 10–20%. Uncomfortable but normal — happens every year or two.',
    'recession':        'When the economy shrinks for two quarters in a row. Often pushes stock prices down.',
    'rally':            'A quick surge in stock prices after a decline — like a bounce-back.',
    'crash':            'A sudden, severe stock market drop — usually 20%+ in a very short period.',
    'dividend':         'A cash payment companies send to shareholders, usually every 3 months. Like a bonus for owning the stock.',
    'dividend yield':   'Annual dividend as a % of the stock price. E.g. 3% yield = $3 paid per $100 of stock.',
    'earnings':         'The profit a company made over a period — after paying all its costs.',
    'revenue':          'All the money a company brought in before paying any expenses.',
    'net income':       'Profit left after every cost, tax, and expense is paid. The bottom-line number.',
    'eps':              'Earnings Per Share — total profit divided by number of shares. Higher = more profitable per share.',
    'earnings per share': 'Total company profit divided by the number of shares. A key indicator of profitability.',
    'gross profit':     'Revenue minus the direct cost of making the product. Before rent, salaries etc.',
    'profit margin':    'What % of revenue a company keeps as profit. 20% margin = $20 kept per $100 earned.',
    'capital gains':    'The profit you make when you sell an investment for more than you paid.',
    'capital loss':     'When you sell an investment for less than you paid — a realized loss.',
    'return on investment': 'How much you earned vs what you put in, shown as a %. 50% ROI = you doubled your money halfway.',
    'roi':              'Return on Investment — profit divided by original cost. Tells you if an investment was worth it.',
    'compound interest': 'Earning returns on your returns. Your money snowballs over time — the longer you wait, the bigger it grows.',
    'cost basis':       'The original price you paid for an investment. Used to calculate your taxable gain or loss.',
    'p/e ratio':        'Price-to-Earnings — how much you pay for $1 of profit. P/E of 20 means investors pay $20 per $1 earned.',
    'p/e':              'Price-to-Earnings ratio. Lower can mean cheaper, but compare to similar companies first.',
    'market cap':       'Total value of all a company's shares combined. Apple at $3T = 3 trillion dollars of total ownership.',
    'valuation':        'An estimate of what a company is actually worth — not always the same as market cap.',
    'undervalued':      'When a stock price is lower than what analysts believe the company is actually worth.',
    'overvalued':       'When a stock price is higher than what the company appears to be worth — could mean a drop is coming.',
    'intrinsic value':  'The true estimated worth of a company based on its finances, not just what the market says.',
    'volatility':       'How wildly a stock price swings. High volatility = big ups and downs. Low = calm and steady.',
    'volume':           'How many shares were bought and sold today. High volume = lots of activity.',
    'liquidity':        'How quickly you can sell an investment for cash without moving the price.',
    'portfolio':        'All the investments you own together — stocks, ETFs, etc.',
    'diversification':  'Spreading money across many different investments to lower your risk.',
    'rebalancing':      'Adjusting your investments back to your original target mix after prices shift.',
    'asset allocation': 'How you split your money between different types of assets like stocks, bonds, and cash.',
    'risk tolerance':   'How comfortable you are with your investments losing value temporarily.',
    'short selling':    'Borrowing shares to sell now, hoping to buy them back cheaper later and keep the difference.',
    'short squeeze':    'When short sellers are forced to buy back shares quickly, causing a rapid price spike.',
    'margin':           'Borrowed money used to buy more stock than you have cash for. Amplifies both gains and losses.',
    'margin call':      'Your broker demands you add cash because your borrowed-stock losses got too large.',
    'stop loss':        'An automatic sell order that kicks in if a stock falls to a price you set — limits your losses.',
    'limit order':      'An order to buy or sell only at a specific price you choose — no worse deal guaranteed.',
    'market order':     'An order to buy or sell immediately at whatever the current price is.',
    'hedge':            'An investment made specifically to reduce the risk of another investment.',
    'hedge fund':       'An aggressive fund using complex strategies, usually for wealthy or institutional investors.',
    'buyback':          'When a company buys its own shares from investors — usually signals confidence and boosts the price.',
    'stock split':      'Company divides each share into more shares at a lower price. E.g. 1 share at $1000 → 10 shares at $100.',
    'merger':           'Two companies combine into one new company — usually announced with a premium on the share price.',
    'acquisition':      'One company buys and takes control of another.',
    'ipo':              'Initial Public Offering — the first time a private company sells shares to the general public.',
    'guidance':         'A company\'s own forecast for its future sales or earnings — markets react strongly to this.',
    'analyst':          'A finance professional who researches companies and sets price targets for stocks.',
    'earnings report':  'A quarterly update companies must release showing their revenue and profit.',
    'sec filing':       'Official financial documents companies must file with the U.S. securities regulator.',
    'fiscal quarter':   'One of four 3-month periods a company uses to report its finances (Q1–Q4).',
    'annual report':    'A yearly summary of a company\'s finances and performance, sent to shareholders.',
    'interest rate':    'The cost of borrowing money. When rates rise, stocks often fall as borrowing becomes expensive.',
    'inflation':        'When everyday prices rise over time and each dollar buys a little less.',
    'federal reserve':  'The U.S. central bank. It sets interest rates and greatly influences the stock market.',
    'yield':            'Income earned from an investment, expressed as a % of its price.',
    'nasdaq':           'A major U.S. stock exchange — home to many tech giants like Apple, Google, and Microsoft.',
    'dow jones':        'An index tracking 30 large U.S. companies — one of the oldest market benchmarks.',
    'fundamental analysis': 'Researching a company\'s finances and business model to estimate what it is truly worth.',
    'technical analysis':   'Studying price charts and trading patterns to predict future price movements.',
    'moving average':       'The average price over a set number of past days — smooths out day-to-day noise.',
    'blue chip':        'A large, well-established, financially stable company with a long track record.',
    'growth stock':     'A company expected to grow faster than average — often reinvests profits instead of paying dividends.',
    'value stock':      'A stock trading below what analysts think it is worth — like a sale on a solid company.',
    'penny stock':      'A stock trading below $5, usually in tiny or unproven companies. Very risky.',
    'options':          'Contracts that give the right (but not obligation) to buy or sell a stock at a set price later.',
    'futures':          'Contracts to buy or sell something at a predetermined price on a future date.',
    'debt-to-equity':   'How much a company owes vs what it owns. Lower is generally safer.',
    'balance sheet':    'A financial snapshot showing what a company owns (assets), owes (debts), and is worth (equity).',
    'cash flow':        'Net cash moving in and out of a business. Positive = company is generating real money.',
    'insider trading':  'Illegally buying or selling stock using private information not available to the public.'
};

/**
 * Highlight fintech terms in text — each term highlighted only on its FIRST occurrence.
 * @param {string} text  - plain text (or already partially HTML)
 * @param {Set}    seen  - shared Set across multiple paragraphs; pass the same instance for one document
 */
function highlightTerms(text, seen) {
    if (!text) return text;
    if (!seen) seen = new Set();
    let result = text;
    Object.keys(fintechTerms)
        .sort((a, b) => b.length - a.length)   // longest match first
        .forEach(term => {
            const key = term.toLowerCase();
            if (seen.has(key)) return;           // already highlighted earlier in the document
            const esc = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const def = fintechTerms[term].replace(/"/g, '&quot;');
            let found = false;
            result = result.replace(new RegExp('\\b' + esc + '\\b', 'gi'), m => {
                if (!found) {
                    found = true;
                    seen.add(key);
                    return `<span class="fintech-term" data-definition="${def}">${m}</span>`;
                }
                return m;   // subsequent occurrences — no highlight
            });
        });
    return result;
}

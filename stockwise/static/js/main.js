
// Watchlist add
document.addEventListener('DOMContentLoaded', function() {
	const form = document.getElementById('watchlist-form');
	const tickerInput = document.getElementById('watchlist_ticker');
	const errorDiv = document.getElementById('watchlist-error');
	const suggestionsList = document.getElementById('ticker-suggestions');

	// Live ticker suggestions
	let debounceTimeout = null;
	if (tickerInput && suggestionsList) {
		tickerInput.addEventListener('input', function() {
			const val = tickerInput.value.trim();
			if (debounceTimeout) clearTimeout(debounceTimeout);
			if (!val) {
				suggestionsList.style.display = 'none';
				suggestionsList.innerHTML = '';
				return;
			}
			debounceTimeout = setTimeout(() => {
				fetch('/search_tickers?q=' + encodeURIComponent(val))
					.then(res => res.json())
					.then(data => {
						suggestionsList.innerHTML = '';
						if (data.length === 0) {
							suggestionsList.style.display = 'none';
							return;
						}
						data.forEach(item => {
							const li = document.createElement('li');
							li.textContent = item.symbol + (item.description ? ' — ' + item.description : '');
							li.setAttribute('data-symbol', item.symbol);
							li.className = 'ticker-suggestion-item';
							li.addEventListener('mousedown', function(e) {
								e.preventDefault();
								tickerInput.value = item.symbol;
								suggestionsList.style.display = 'none';
								suggestionsList.innerHTML = '';
							});
							suggestionsList.appendChild(li);
						});
						suggestionsList.style.display = 'block';
					});
			}, 200);
		});
		// Hide suggestions on blur
		tickerInput.addEventListener('blur', function() {
			setTimeout(() => {
				suggestionsList.style.display = 'none';
			}, 150);
		});
	}

	if (form) {
		form.addEventListener('submit', function(e) {
			e.preventDefault();
			errorDiv.style.display = 'none';
			const ticker = tickerInput.value.trim();
			if (!ticker) return;
			fetch('/add_watchlist', {
				method: 'POST',
				headers: {'Content-Type': 'application/x-www-form-urlencoded'},
				body: 'watchlist_ticker=' + encodeURIComponent(ticker)
			})
			.then(res => res.json())
			.then(data => {
				if (data.success) {
					window.location.reload();
				} else {
					errorDiv.textContent = data.error || 'Could not add to watchlist.';
					errorDiv.style.display = 'block';
				}
			})
			.catch(() => {
				errorDiv.textContent = 'Could not add to watchlist.';
				errorDiv.style.display = 'block';
			});
		});
	}

	// Remove from watchlist
	document.querySelectorAll('.remove-btn').forEach(btn => {
		btn.addEventListener('click', function(e) {
			e.preventDefault();
			const symbol = btn.getAttribute('data-symbol');
			fetch('/remove_watchlist', {
				method: 'POST',
				headers: {'Content-Type': 'application/x-www-form-urlencoded'},
				body: 'symbol=' + encodeURIComponent(symbol)
			})
			.then(res => res.json())
			.then(data => {
				if (data.success) {
					window.location.reload();
				}
			});
		});
	});
});

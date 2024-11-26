# global modules

import numpy as np
import yfinance as yf
# import random
import time
# import os
from new2 import correct_times_prices
import requests

import logging
logger = logging.getLogger('yfinance')
logger.disabled = True
logger.propagate = False



name = 'XTRACKERS EURO STOXX 50 ETF'
isin = 'LU0380865021'


START_PORTFOLIO = '2023-05-01'
today = str(np.datetime64('today', 'D'))
Currencies = {'EUR': 1}


def get_ticker(company_name, isin):
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    company_name = company_name.replace('ETF', '') # remove ETF because it does not like it
    params = {"q": company_name, "quotes_count": 1, "country": "United States"}
    # params = {"q": company_name, "quotes_count": 15, "country": "Austria"}

    res = requests.get(url=url, params=params, headers={'User-Agent': user_agent})
    data = res.json()
    results = data['quotes']

    symbols = []
    for result in results:
        symbols.append(result['symbol'])

    return symbols


def get_data(company_name, isin):
    waiting_time = 2

    company_name = company_name.replace('ETF', '')
    # search = [isin, company_name] + get_ticker(company_name, isin)
    search = [isin] + get_ticker(company_name, isin)
    for i in range(len(search)):
        if i > 0:
            print('WARNING: ticker could be wrong')
            print(company_name, search[i])
            # return np.array([]), np.array([])
        s = search[i]
        time.sleep(waiting_time)
        data = yf.download(s, START_PORTFOLIO, today, interval='1d', progress=False)
        data = data.dropna(axis=1, how='all')
        s_index = s.split(' ')[0] # spaces and index names are weired in pandas, pandas splits with spaces
        if len(data) != 0:
            print(company_name, s)
            price_history = data[('Close', s_index)].to_numpy()
            Time = data[('Close', s_index)].index.to_numpy().astype('datetime64[D]')
            Time, price_history = correct_times_prices(Time, price_history, START_PORTFOLIO, today)

            time.sleep(waiting_time)
            ticker = yf.Ticker(s)
            currency = ticker.info['currency']

            if currency not in Currencies:
                time.sleep(waiting_time)
                change = yf.Ticker('EUR{}=X'.format(currency))
                eur_change = change.info['ask'] # bid/ask
                Currencies[currency] = eur_change
            price_history = price_history / Currencies[currency]

            return Time, price_history

    return np.array([]), np.array([])





# else download history

# ticker_symbol = get_ticker(name.replace('ETF', '')) # it does not like the word ETF
ticker_symbol = get_ticker(name, isin) # it does not like the word ETF
# data = yf.download(isin, START_PORTFOLIO, today, interval='1d')
data = yf.download(ticker_symbol, START_PORTFOLIO, today, interval='1d')
price_history = data[('Close', isin)].to_numpy()
Time = data[('Close', isin)].index.to_numpy().astype('datetime64[D]')

Time, price_history = correct_times_prices(Time, price_history, START_PORTFOLIO, today)


# ticker = yf.Ticker(isin)
ticker = yf.Ticker(ticker_symbol)
currency = ticker.info['currency']
# hist = ticker.history(start=START_PORTFOLIO, end=today)
# time = hist.index.date

if currency not in Currencies:
    change = yf.Ticker('EUR{}=X'.format(currency))
    eur_change = change.info['ask'] # bid/ask
    Currencies[currency] = eur_change
print('after exchange')

price_history = price_history / Currencies[currency]






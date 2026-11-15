import numpy as np
import requests
import random
import time
import yfinance as yf
import logging
from importlib import reload

logger = logging.getLogger('yfinance')
logger.disabled = True
logger.propagate = False

import TickerList as tl
reload(tl)


Currencies = {'EUR': 1}

################################################################################
# Functions 

# Saturdays and Sundays are missing and sometimes the valuta date is on these days
def correct_times_prices(times, prices, start, end):
    if len(prices) == 0:
        return times, prices

    dt_start = np.datetime64(start, 'D')
    dt_end = np.datetime64(end, 'D')

    new_times = [dt_start]
    new_prices = [prices[0]]
    delta = np.timedelta64(1, 'D')

    counter = 0
    COUNTER_LIMIT = 10000
    while new_times[-1] != times[0]:
        new_times.append(new_times[-1]+delta)
        new_prices.append(new_prices[-1])
        counter += 1
        if counter > COUNTER_LIMIT:
            raise Exception('While Loop Error') # pretty bad solution

    for i in range(1, len(times)):
        while new_times[-1] + delta != times[i]:
            new_times.append(new_times[-1]+delta)
            # print(new_times[-1])
            new_prices.append(new_prices[-1])
            counter += 1
            if counter > COUNTER_LIMIT:
                raise Exception('While Loop Error')

        new_times.append(times[i])
        new_prices.append(prices[i])

    while new_times[-1] != dt_end:
        new_times.append(new_times[-1]+delta)
        new_prices.append(new_prices[-1])
        counter += 1
        if counter > COUNTER_LIMIT:
            raise Exception('While Loop Error')


    return np.array(new_times), np.array(new_prices)



def get_ticker(company_name, isin):
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    company_name = company_name.replace('ETF', '') # remove ETF because it does not like it
    params = {"q": company_name, "quotes_count": 1, "country": "United States"}
    # params = {"q": company_name, "quotes_count": 15, "country": "Austria"}

    try:
        res = requests.get(url=url, params=params, headers={'User-Agent': user_agent})
        data = res.json()
        results = data['quotes']

        symbols = []
        for result in results:
            symbols.append(result['symbol'])
    except:
        symbols = []

    return symbols


def get_data(start_date, company_name, isin):
    today = str(np.datetime64('today', 'D'))
    waiting_time = 1 + random.random() # yahoo checks if you download much in short time

    company_name = company_name.replace('ETF', '')
    if isin in tl.TickerList:
        search = [tl.TickerList[isin], isin, company_name] + get_ticker(company_name, isin)
    else:
        search = [isin, company_name] + get_ticker(company_name, isin)
    # search = [isin, company_name] + get_ticker(company_name, isin)
    # search = [isin] + get_ticker(company_name, isin)
    try:
        for i in range(len(search)):
            s = search[i]
            time.sleep(waiting_time)
            data = yf.download(s, start_date, today, interval='1d', progress=False)
            data = data.dropna(axis=1, how='all')
            s_index = s.split(' ')[0] # spaces and index names are weired in pandas, pandas splits with spaces
            if len(data) != 0:
                if i > 0:
                    print('    -> WARNING: ticker could be wrong')
                    print('    {}, {}, {}'.format(company_name, isin, search[i]))
                price_history = data[('Close', s_index)].to_numpy()
                Time = data[('Close', s_index)].index.tz_convert(None).to_numpy().astype('datetime64[D]')
                Time, price_history = correct_times_prices(Time, price_history, start_date, today)

                time.sleep(waiting_time)
                ticker = yf.Ticker(s)
                if 'currency' not in ticker.info:
                    print('Currency not found.')
                    break # something is wrong
                currency = ticker.info['currency']

                if currency not in Currencies:
                    time.sleep(waiting_time)
                    change = yf.Ticker('EUR{}=X'.format(currency))
                    eur_change = change.info['ask'] # bid/ask
                    Currencies[currency] = eur_change
                price_history = price_history / Currencies[currency]

                return Time, price_history
    except Exception as e:
        print('error with', company_name, isin)
        print(e)

    return np.array([]), np.array([])

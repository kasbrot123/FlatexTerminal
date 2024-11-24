

import pandas as pd
from matplotlib import pyplot as plt
import datetime as dt
import numpy as np

import yfinance as yf

"""


Orders
Kontoumsätze


Problem: Eurostoxx zeigt falschen wert an




"""


# t = np.arange(dt.datetime(2023,5,1), dt.datetime(2015,7,1), dt.timedelta(days=1)).astype(dt.datetime)



import datetime as dt
t = np.arange(dt.datetime(2023,5,1), dt.datetime.today(), dt.timedelta(days=1)).astype(dt.datetime)


x = range(len(t))



# microsoft = yfinance.Ticker('MSF.DE')
# daten = microsoft.basic_info
# print(f'{daten.last_price:.2f} {daten.currency}')
#
#
# Kurs = microsoft.history(period=str(len(t))+'d', interval='1d')

ticker = 'AMZN'
data = yf.download(ticker, '2023-05-01', '2024-11-17')

# plt.plot(data.)



plt.show()

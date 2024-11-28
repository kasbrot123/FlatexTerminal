import numpy as np
import os
from matplotlib import pyplot as plt
from functions import get_data


class Wertpapier():

    def __init__(self, isin, name, start_date):

        self.isin = isin
        self.name = name

        self.dates = []
        self.prices = []
        self.nominals = []
        self.values_netto = []
        self.values_brutto = []

        self.stock_value = 0
        self.Absolut = 0
        self.Relativ = 1

        print(self.name)

        cache_file = '.caching'+os.sep+isin+'.npy'
        if os.path.isfile(cache_file):
            data = np.load(cache_file, allow_pickle=True)
            data_time = data[0].astype(np.datetime64)
            if len(data_time) > 0 and data_time[-1] >= np.datetime64('today', 'D'):
                print(name, isin, 'caching...')
                self.time = data_time
                self.price_history = data[1]
                return

        # today = str(np.datetime64('today', 'D'))
        self.time, self.price_history = get_data(start_date, self.name, self.isin)
        np.save(cache_file, [self.time, self.price_history])



    def add(self, date, value, nominal, price):
        self.dates.append(date)
        self.values_netto.append(value)
        self.values_brutto.append(np.nan)
        self.nominals.append(nominal)
        self.prices.append(price)
        self.stock_value = sum([p*n for p, n in zip(self.prices, self.nominals)])


    def split(self, split):
        self.prices = [p * split for p in self.prices]
        self.nominals = [n / split for n in self.nominals]


    def plot(self):
        if len(self.values_netto) != 0:
            values_cumsum = np.cumsum(self.values_netto)
            plt.plot(self.dates, values_cumsum, 'o--', label='{} ({:0.2f} €)'.format(self.name, values_cumsum[-1]))


    def time_update(self):
        self.t_nominals = np.zeros(len(self.time))
        self.t_prices = np.zeros(len(self.time))

        for i in range(len(self.dates)):
            L = self.time == self.dates[i]
            self.t_nominals[L] += self.nominals[i]
            self.t_prices[L] = self.prices[i]

        self.tsum_nominals = np.cumsum(self.t_nominals)

        self.t_nominals_buy = np.copy(self.t_nominals)
        self.t_nominals_buy[self.t_nominals_buy < 0] = 0
        
        effective_price = np.cumsum(self.t_nominals_buy * self.t_prices) / np.cumsum(self.t_nominals_buy)

        self.Absolut = self.price_history * self.tsum_nominals
        self.Absolut[self.Absolut == 0] = 0
        L_nominal = self.tsum_nominals > 0
        self.Relativ = self.price_history / effective_price * L_nominal



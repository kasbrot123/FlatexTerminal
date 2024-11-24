"""

yfinance probleme bei
    ETFS 
    Super Micro Computer
    JPM Call auf Tesla
    Xetra Gold


ToDo
    - ETFs funktionieren nicht
    - Calls / Gold / Super Micro Computer lösen
    - Export Depotumsätze nicht vollständig (Konto schon)
    - Gesamt gegenrechnen: KontoSaldo + Depot = 50.000 irgendwas
    - Vielleicht die Aktien bei komplettem Verkauf trennen sodass neuer eff. Preis entsteht
    - xlsx and csv support


Konten:

    Tracking:
        - Depot Zuflüsse (DepotIn)
        - Depot Abflüsse (DepotOut)
        - Konto Zuflüsse (KontoIn)
        - Konto Abflüsse (KontoOut)
        - Einzahlungen (CashIn)
        - Auszahlungen (CashOut)
        - Dividenden nach Steuer (Dividends)


    Calculated:
        KontoSaldo = 
            KontoZuflüsse - KontoAbflüsse
            (KontoSum)

        DepotWert = 
            Summe{ Wert aller Wertpapiere }
            (DepotSum)

        GebührSteuer = 
            (KontoZuflüsse - KontoAbflüsse) - (DepotAbflüsse - DepotZuflüsse)
            (FeesTaxes)

        GesamtPortfolio = 
            KontoSaldo + DepotWert
            (Portfolio)


"""



# global modules
import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
import datetime as dt
import yfinance as yf
import random
import time
import os


# local modules
from interactive_legend import InteractiveLegend


####################################
# Global Definitions 


START_PORTFOLIO = '2023-05-01'
Currencies = {'EUR': 1}


####################################
# Paths and Folders

if not os.path.isdir('./.caching'):
    os.mkdir('.caching')

# files with data
# if not os.path.isdir('./data'):
#     os.mkdir('./data')


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

################################################################################
# Classes 

class Konto():
    def __init__(self, name):
        self.name = name
        self.dates = []
        self.values = []
        self.value = 0

        start = np.datetime64(START_PORTFOLIO, 'D')
        end = np.datetime64('today', 'D')

        self.time = np.arange(start, end, np.timedelta64(1, 'D'))
        self.t_values = np.zeros(len(self.time))


    def add(self, date, value):
        self.value += value
        self.dates.append(date)
        self.values.append(value)

        # update time vectors
        # one could do this in the end
        # would be faster without recalculating cumsum
        L = self.time == date
        self.t_values[L] += value
        self.tsum_values = np.cumsum(self.t_values)


    def plot(self, everyday=False):
        if len(self.values) != 0:
            if everyday:
                plt.plot(self.time, self.tsum_values, '-', label='{} ({:0.2f} €)'.format(self.name, self.t_values[-1]))
            else:
                values_cumsum = np.cumsum(self.values)
                plt.plot(self.dates, values_cumsum, 'o--', label='{} ({:0.2f} €)'.format(self.name, values_cumsum[-1]))


    # def __add__(self, other):
    #
    #     # some test if other is the same object
    #     # ...
    #
    #     self.values = 
    #     Sum = Konto('sum')
    #     Sum.values 



class Wertpapier():

    def __init__(self, isin, name):

        self.isin = isin
        self.name = name

        self.dates = []
        self.prices = []
        self.nominals = []
        self.values_netto = []
        self.values_brutto = []

        self.stock_value = 0

        try:
            today = str(np.datetime64('today', 'D'))

            cache_file = '.caching'+os.sep+isin+'.npy'
            if os.path.isfile(cache_file):
                data = np.load(cache_file, allow_pickle=True)
                data_time = data[0].astype(np.datetime64)
                if len(data_time) > 0 and data_time[-1] >= np.datetime64('today', 'D'):
                    print('caching...')
                    self.time = data_time
                    self.price_history = data[1]
                    return

            # else download history

            data = yf.download(self.isin, START_PORTFOLIO, today, interval='1d')
            self.price_history = data[('Close', self.isin)].to_numpy()
            self.time = data[('Close', self.isin)].index.to_numpy().astype('datetime64[D]')

            self.time, self.price_history = correct_times_prices(self.time, self.price_history, START_PORTFOLIO, today)


            time.sleep(1+random.random())
            print('after history')

            ticker = yf.Ticker(self.isin)
            currency = ticker.info['currency']
            # hist = ticker.history(start=START_PORTFOLIO, end=today)
            # self.time = hist.index.date
            time.sleep(1+random.random())
            print('after currency')

            if currency not in Currencies:
                change = yf.Ticker('EUR{}=X'.format(currency))
                eur_change = change.info['ask'] # bid/ask
                Currencies[currency] = eur_change
            print('after exchange')

            self.price_history = self.price_history / Currencies[currency]
            time.sleep(2*random.random()+2)

            # save for caching
            np.save(cache_file, [self.time, self.price_history])

        except Exception as e:
            print('yfinance exception')
            print(self.name, self.isin)
            self.price_history = []


    def add(self, date, value, nominal, price):
        self.dates.append(date)
        self.values_netto.append(value)
        self.values_brutto.append(np.nan)
        self.nominals.append(nominal)
        self.prices.append(price)


    def split(self, split):
        self.prices = [p * split for p in self.prices]
        self.nominals = [n / split for n in self.nominals]


    def plot(self):
        if len(self.values_netto) != 0:
            values_cumsum = np.cumsum(self.values_netto)
            plt.plot(self.dates, values_cumsum, 'o--', label='{} ({:0.2f} €)'.format(self.name, values_cumsum[-1]))


    def Value(self):
        # self.stock_value = sum(self.nominals) * self.price_current
        self.stock_value = sum([p*n for p, n in zip(self.prices, self.nominals)])
        return self.stock_value

    def time_update(self):
        self.t_nominals = np.zeros(len(self.time))
        self.t_prices = np.zeros(len(self.time))

        for i in range(len(self.dates)):
            L = self.time == self.dates[i]
            self.t_nominals[L] += self.nominals[i]
            self.t_prices[L] = self.prices[i]
            if not any(L):
                print('MISSING DATE')
            else:
                print('Found one day',any(L))

        self.tsum_nominals = np.cumsum(self.t_nominals)

        self.t_nominals_buy = np.copy(self.t_nominals)
        self.t_nominals_buy[self.t_nominals_buy < 0] = 0
        
        effective_price = np.cumsum(self.t_nominals_buy * self.t_prices) / np.cumsum(self.t_nominals_buy)

        self.Absolut = self.price_history * self.tsum_nominals
        self.Absolut[self.Absolut == 0] = 0
        L_nominal = self.tsum_nominals > 0
        self.Relativ = self.price_history / effective_price * L_nominal


class Terminal():

    def __init__(self):
        ## init parameters and 'Konten'
        pass

    def read_data(self):
        # read the data from the files and evaluate
        pass

    def plot_konten(self):
        # plot all 'Konten' with interactive mode
        pass

    def plot_stocks(self, relative=True):
        # plot all stock data abs/rel values with interative mode
        pass


    # single analysis of stocks and other stuff on demand





################################################################################




#################################################################
# this should all be stored in another class

depot_path = './Depotumsätze_2023_2024.xlsx'
konto_path = './Kontoumsätze_2023_2024.xlsx'

depot = pd.read_excel(depot_path)
konto = pd.read_excel(konto_path)


# make sure konto is sorted for date (Valuta or Buchungsdatum)
konto_valuta = konto['Valuta'].to_numpy()
konto_info = konto['Buchungsinformationen'].to_numpy()
konto_betrag = konto['Betrag'].to_numpy()

depot_date = depot['Buchungstag'].to_numpy().astype('datetime64[D]') # this is more accurate than Valuta
# depot_date = depot['Valuta'].to_numpy()
depot_bezeichnung = depot['Bezeichnung'].to_numpy()
depot_isin = depot['ISIN'].to_numpy()

depot_nominal = depot['Nominal (Stk.)'].to_numpy()
depot_betrag = depot['Betrag'].to_numpy()
depot_kurs = depot['Kurs'].to_numpy()

depot_info = depot['Buchungsinformation'].to_numpy()


#################################################################


# number of lines with 'Ausf'
# depot['Buchungsinformation'].str.contains('Ausf').sum()

Eigenkapital_keys = [
    'Einlage',
    'Flatex Auszahlung',
    'Investment',
    'Investment Sparplan'
    ]
Order_keys = ['ORDER']

Eigenkapital_Konto = Konto('Eigenkapital')
Order_Konto = Konto('Orders')
KontoSaldo = Konto('Konto Saldo')
Wertpapiere = []




# iteration for depot
for i in range(len(depot)):
    date = depot_date[i]
    info = depot_info[i]

    ISIN = depot_isin[i]
    nominal = depot_nominal[i]
    value_netto = depot_betrag[i] # value without charges
    value_brutto = depot_betrag[i] # value with charges, money you spend
    price = depot_kurs[i]

    name = depot_bezeichnung[i]

    if 'Ausführung' in info:
        not_in_Wertpapiere = True
        for w in Wertpapiere:
            if w.isin == ISIN:
                not_in_Wertpapiere = False
                w.add(date, value_netto, nominal, price)
        if not_in_Wertpapiere:
            w = Wertpapier(ISIN, name)
            w.add(date, value_netto, nominal, price)
            Wertpapiere.append(w)


    if 'Split' in info:
        if value_netto > 0: # split appears twice
            not_in_Wertpapiere = True
            x = info.split(' ')
            for y in x:
                if ':' in y:
                    a, b = y.split(':')
                    split = float(a) / float(b)
                    print(a, b)

            for w in Wertpapiere:
                if w.isin == ISIN:
                    w.split(split)

    # break # safety break


# iteration for konto
for i in range(len(konto_valuta)):
    date = konto_valuta[i]
    buchungsinfo = konto_info[i]
    value_konto = konto_betrag[i]

    KontoSaldo.add(date, value_konto)

    if any(key in buchungsinfo for key in Eigenkapital_keys):
        Eigenkapital_Konto.add(date, value_konto)
        continue

    if any(key in buchungsinfo for key in Order_keys):
        Order_Konto.add(date, value_konto)
        continue

plt.figure()
for i in range(len(Wertpapiere)):
    w = Wertpapiere[i]
    w.time_update()
    if len(w.time) == 0:
        continue
    plt.plot(w.time, w.Absolut, label=w.name+str(i))
plt.legend()
plt.grid()
leg1 = InteractiveLegend()

plt.figure()
for i in range(len(Wertpapiere)):
    w = Wertpapiere[i]
    if len(w.time) == 0:
        continue
    plt.plot(w.time, w.Relativ, label=w.name+str(i))
plt.legend()
plt.grid()
leg = InteractiveLegend()



# Portfolio_Value = 0
# for w in Wertpapiere:
#     if len(w.Absolut) > 0:
#         if np.isnan(w.Absolut[-1]):
#             continue
#         Portfolio_Value += w.Absolut[-1]
#     else: # fechting of stock data was not passible
#         Portfolio_Value += w.Value()
#         print(w.name, w.Value())
#         # print(w.Absolut[-1])

# # Portfolio_Value = sum([w.Absolut[-1] for w in Wertpapiere if len(w.Absolut) > 0])
# Gesamt_Value = Portfolio_Value + sum(KontoSaldo.values)
# print('Gesamt Value:', Gesamt_Value)


plt.figure()
w.plot()
Eigenkapital_Konto.plot()
Order_Konto.plot()
KontoSaldo.plot()
plt.grid()
plt.legend()


plt.show()





###############################################################################
# Other Stuff


# from googlefinance import getQuotes
# import json
#
# x = json.dumps(getQuotes('AAPL'), indent=2)
#
# y = json.dumps(getQuotes(['AAPL', 'VIE:BKS']), indent=2)

"""

Kontoumsätze für genaue Abrechnung
    -> Gebühren und Steuer ist bereits abgezogen etc.
    -> Das sind die Wichtigen Events

Depotumsätze
    -> sagen mir wiehoch der Kurs war
    -> Lookup wieviel geld ich vor Steuern/Gebühr bekomme
    -> Berechnung von realem Gewinn
    -> 


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
    - Konten einrichten für: Gebühr, Steuer, Devisen etc.
    - Konten auf Zeitvektor richten
    - xlsx and csv support
    - Mehrere Käufe an einem Tag -> Problem
    - UTC time tz_localize Fuckup lösen (comparing A == B funtioniert nicht)


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


START_PORTFOLIO = '2023-05-01'

Currencies = {'EUR': 1}


if not os.path.isdir('./.chaching'):
    os.mkdir('.chaching')


# files with data
# if not os.path.isdir('./data'):
#     os.mkdir('./data')


class Konto():
    def __init__(self, name):
        self.name = name
        self.dates = []
        self.values = []
        self.value = 0

    def add(self, date, value):
        self.value += value
        self.dates.append(date.tz_localize('UTC'))
        self.values.append(value)

    def plot(self, everyday=False):

        if len(self.values) != 0:
            if everyday:
                self.time_update()
                plt.plot(self.time, self.tsum_values, '-', label='{} ({:0.2f} €)'.format(self.name, self.t_values[-1]))
            else:
                values_cumsum = np.cumsum(self.values)
                plt.plot(self.dates, values_cumsum, 'o--', label='{} ({:0.2f} €)'.format(self.name, values_cumsum[-1]))



    def time_update(self):
        start = pd.Timestamp(int(START_PORTFOLIO[0:4]), int(START_PORTFOLIO[5:7]), int(START_PORTFOLIO[8:10])).tz_localize('UTC')
        end = pd.Timestamp(dt.datetime.today().date()).tz_localize('UTC')
        self.time = np.arange(start, end, dt.timedelta(days=1))
        self.time = np.array([i.tz_localize('UTC') for i in self.time]) # i hate it but i am too lazy
        self.t_values = np.zeros(len(self.time))

        for i in range(len(self.dates)):
            date = self.dates[i]
            L = self.time == date
            self.t_values[L] += self.values[i]

        self.tsum_values = np.cumsum(self.t_values)


    # def __add__(self, other):
    #
    #     # some test if other is the same object
    #     # ...
    #
    #     self.values = 
    #     Sum = Konto('sum')
    #     Sum.values 




# class Wertpapier():
#
    # def __init__(self, ID, name):
    #
    #     self.ID = ID
    #     self.name = name
    #
    #     self.date = []
    #     self.konto = []
    #     self.depot = []
    #     self.kurs = []
    #     # self.kurs_mean = []
    #     self.stueck = []
    #     self.gewinn = []
    #     self.gebuehr = []
    #
    #     self.n_stocks = 0
    #     self.mean_price = 0
    #
    # def buy(self, date, value_konto, value_depot, number, kurs):
    #     self.date.append(date)
    #     self.konto.append(value_konto)
    #     self.depot.append(value_depot)
    #     self.stueck.append(number)
    #     self.kurs.append(kurs)
    #     self.gewinn.append(0)
    #     self.gebuehr.append(-value_konto-value_depot)
    #
    #     self.mean_price = (self.n_stocks * self.mean_price + number * kurs)/(self.n_stocks + number)
    #     self.n_stocks += number
    #
    #
    #
    # def sell(self, date, value_konto, value_depot, number, kurs):
    #     self.date.append(date)
    #     self.konto.append(value_konto)
    #     self.depot.append(value_depot)
    #     self.stueck.append(number)
    #     self.kurs.append(kurs)
    #     self.gebuehr.append(-value_konto-value_depot)
    #
    #     self.gewinn.append(value_konto-number*self.mean_price)
    #     self.n_stocks -= number


def michi(a, b):
    Currencies[a] = b
    return

# Saturdays and Sundays are missing and sometimes the valuta date is on these days
def correct_times_prices(times, prices, start, end):
    if len(prices) == 0:
        return times, prices

    dt_start = pd.Timestamp(int(start[0:4]), int(start[5:7]), int(start[8:10])).tz_localize('UTC')
    dt_end = pd.Timestamp(int(end[0:4]), int(end[5:7]), int(end[8:10])).tz_localize('UTC')

    new_times = [dt_start]
    new_prices = [prices[0]]
    delta = dt.timedelta(days=1)

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
            print(new_times[-1])
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

        # try:
        #     ticker = yf.Ticker(self.isin)
        #     self.price_current = ticker.info['currentPrice']
        # except:
        #     print('Problems with ' + self.name)
        #     self.price_current = 0

        try:
            today = dt.datetime.today().strftime("%Y-%m-%d")


            cache_file = '.caching'+os.sep+isin+'.npy'
            if os.path.isfile(cache_file):
                print('caching...')
                data = np.load(cache_file, allow_pickle=True)
                # Time = data[0]
                # if time[0] == XXX and time[-1] == dt.datetime.today():
                self.time = data[0]
                self.price_history = data[1]
                return

            # else download history

            data = yf.download(self.isin, START_PORTFOLIO, today, interval='1d')
            self.price_history = data[('Close', self.isin)].to_numpy()
            self.time = data[('Close', self.isin)].index.to_numpy()
            self.time, self.price_history = correct_times_prices(self.time, self.price_history, START_PORTFOLIO, today)
            
            # self.time = np.arange(dt.datetime(2023, 5, 1), dt.datetime.today(), dt.timedelta(days=1)).astype(dt.datetime)
        # N = len(self.time)
        # self.number_t = np.zeros(N)
            
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


        # self.time = np.arange(dt.datetime(2023, 5, 1), dt.datetime.today(), dt.timedelta(days=1)).astype(dt.datetime)
        # N = len(self.time)
        # self.number_t = np.zeros(N)

        # # change to isin
        # ticker = 'AMZN'


    def add(self, date, value, nominal, price):
        self.dates.append(date)
        self.values_netto.append(value)
        self.values_brutto.append(np.nan)
        self.nominals.append(nominal)
        self.prices.append(price)

        # self.Value()


    def split(self, split):
        self.prices = [p * split for p in self.prices]
        self.nominals = [n / split for n in self.nominals]

        # self.Value()

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


# from googlefinance import getQuotes
# import json
#
# x = json.dumps(getQuotes('AAPL'), indent=2)
#
# y = json.dumps(getQuotes(['AAPL', 'VIE:BKS']), indent=2)


'US67066G1040'

depot_path = './Depotumsätze_2023_2024.xlsx'
konto_path = './Kontoumsätze_2023_2024.xlsx'

depot = pd.read_excel(depot_path)
konto = pd.read_excel(konto_path)
depot['Buchungstag'] = pd.to_datetime(depot['Buchungstag'], unit='ms').dt.tz_localize('UTC')
depot['Valuta'] = pd.to_datetime(depot['Valuta'], unit='ms').dt.tz_localize('UTC')
# pd.to_datetime(depot['Buchungstag'], unit='ms').dt.tz_localize('UTC')


# depot = depot.assign(identifier=depot.Buchungsinformation.astype(str).str[-9:])
# konto = konto.assign(identifier=konto.Buchungsinformationen.astype(str).str[-9:])



# make sure konto is sorted for date (Valuta or Buchungsdatum)
konto_valuta = konto['Valuta'].to_list()
konto_info = konto['Buchungsinformationen'].to_list()
konto_betrag = konto['Betrag'].to_list()

depot_date = depot['Buchungstag'].to_list() # this is more accurate
# depot_date = depot['Valuta'].to_list()
depot_bezeichnung = depot['Bezeichnung'].to_list()
depot_isin = depot['ISIN'].to_list()

depot_nominal = depot['Nominal (Stk.)'].to_list()
depot_betrag = depot['Betrag'].to_list()
depot_kurs = depot['Kurs'].to_list()

depot_info = depot['Buchungsinformation'].to_list()


# def return_index(key, array):
#     return array.index(key)


Depotkonto = Konto('Depot')
Einlagenkonto = Konto('Einlage')
Gesamtkonto = Konto('Gesamt')
OhneEinlagen = Konto('Ohne Einlagen')

depot['Buchungsinformation'].str.contains('Ausf').sum()





Wertpapiere = []



counter = 0

for i in range(len(depot)):
    if counter == 2000:
        break
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
            counter += 1


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

    # break



plt.figure()
for i in range(len(Wertpapiere)):
    w = Wertpapiere[i]
    w.time_update()
    plt.plot(w.time, w.Absolut, label=w.name+str(i))
plt.legend()
plt.grid()
leg1 = InteractiveLegend()

plt.figure()
for i in range(len(Wertpapiere)):
    w = Wertpapiere[i]
    plt.plot(w.time, w.Relativ, label=w.name+str(i))
plt.legend()
plt.grid()
leg = InteractiveLegend()


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


Portfolio_Value = 0
for w in Wertpapiere:
    if len(w.Absolut) > 0:
        if np.isnan(w.Absolut[-1]):
            continue
        Portfolio_Value += w.Absolut[-1]
    else: # fechting of stock data was not passible
        Portfolio_Value += w.Value()
        print(w.name, w.Value())
        # print(w.Absolut[-1])

# Portfolio_Value = sum([w.Absolut[-1] for w in Wertpapiere if len(w.Absolut) > 0])
Gesamt_Value = Portfolio_Value + sum(KontoSaldo.values)
print('Gesamt Value:', Gesamt_Value)

"Gesamt Value: 51362.247873116496"

plt.figure()
w.plot()
Eigenkapital_Konto.plot()
Order_Konto.plot()
KontoSaldo.plot()
plt.grid()
plt.legend()


plt.show()



    # if 'Ausführung' in buchungsinfo:
    #
    #     
    #
    #     # index = return_index(konto_info[i], depot_info)
    #     index = depot_info.index(konto_info[i])
    #     value_depot = depot_betrag[index]
    #     number = abs(depot_nominal[index])
    #     kurs = depot_kurs[index]
    #     ISIN = depot_isin[index]
    #     name = depot_bezeichnung[index]
    #
    #     # print(value_konto, value_depot)
    #
    #      # = depot_isin[index]
    #
    #
    #     Einlagenkonto.add(date, value_konto)
    #     Depotkonto.add(date, value_depot)
    #     Gesamtkonto.add(date, value_konto+value_depot)
    #     OhneEinlagen.add(date, value_konto)
    #
    #
    #     not_in_Wertpapiere = True
    #     for w in Wertpapiere:
    #         if w.ID == ISIN:
    #             not_in_Wertpapiere = False
    #             if value_konto < 0:
    #                 # print('bought more')
    #                 w.buy(date, value_konto, value_depot, number, kurs)
    #             if value_konto > 0:
    #                 # print('sold')
    #                 w.sell(date, value_konto, value_depot, number, kurs)
    #
    #
    #
#
#
#         if not_in_Wertpapiere:
#             # print('added wertpapier')
#             wertpapier = Wertpapier(ISIN, name)
#             if value_konto < 0:
#                 wertpapier.buy(date, value_konto, value_depot, number, kurs)
#                 Wertpapiere.append(wertpapier)
#             else:
#                 print("error, something's wrong")
#     # else:
#     #     pass
#         # print('not a order')
#
#     # if i == 1:
#     #     break
#
#     else:
#         # this means everything else than 'Ausführung' is a payment to or from the 'Einlagenkonto' and does not influence the ''
#         Einlagenkonto.add(date, value_konto)
#         Gesamtkonto.add(date, value_konto)
#         if any(note in buchungsinfo for note in ['Einlage', 'Auszahlung', 'Investment']):
#             pass
#         else:
#             OhneEinlagen.add(date, value_konto)
#
#
# Stock_names = [w.name for w in Wertpapiere]
#
# for w in Wertpapiere:
#     if sum(w.gewinn) == 0:
#         continue
#     print('{}: {:0.2f}€'.format(w.name,sum(w.gewinn)))
#
#
#
# Gewinn = sum([sum(w.gewinn) for w in Wertpapiere])
# print('Gewinn Aktien: {:0.2f}€'.format(Gewinn))
#
#
# fig = plt.figure()
# Einlagenkonto.plot()
# Depotkonto.plot()
# Gesamtkonto.plot()
# OhneEinlagen.plot()
# plt.grid()
# plt.legend()
# plt.xlabel('time')
# plt.ylabel('Money in €')
#
# plt.show()



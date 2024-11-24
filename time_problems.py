import pandas as pd
import numpy as np
import datetime as dt


START_PORTFOLIO = '2023-05-01'

depot_path = './Depotumsätze_2023_2024.xlsx'
konto_path = './Kontoumsätze_2023_2024.xlsx'

depot = pd.read_excel(depot_path)
konto = pd.read_excel(konto_path)

# depot['Buchungstag'] = pd.to_datetime(depot['Buchungstag'], unit='ms').dt.tz_localize('UTC')
# depot['Valuta'] = pd.to_datetime(depot['Valuta'], unit='ms').dt.tz_localize('UTC')

dates = depot['Buchungstag'].to_numpy()


# start = pd.Timestamp(int(START_PORTFOLIO[0:4]), int(START_PORTFOLIO[5:7]), int(START_PORTFOLIO[8:10])).tz_localize('UTC')
# end = pd.Timestamp(dt.datetime.today().date()).tz_localize('UTC')


start = dt.datetime.strptime(START_PORTFOLIO, '%Y-%m-%d')
end = dt.datetime.today().date()

time = np.arange(start, end, dt.timedelta(days=1))




start = pd.Timestamp(int(START_PORTFOLIO[0:4]), int(START_PORTFOLIO[5:7]), int(START_PORTFOLIO[8:10])).tz_localize('UTC')
end = pd.Timestamp(dt.datetime.today().date()).tz_localize('UTC')
self.time = np.arange(start, end, dt.timedelta(days=1))
self.time = np.array([i.tz_localize('UTC') for i in self.time]) # i hate it but i am too lazy
self.t_values = np.zeros(len(self.time))




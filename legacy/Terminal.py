import os
import glob
from matplotlib import pyplot as plt
import pandas as pd


# local modules
from InteractiveLegend import InteractiveLegend
from Konto import Konto
from Wertpapier import Wertpapier


FIGSIZE = (14, 7)

class Terminal():

    def __init__(self, start_date):
        ## init parameters and 'Konten'
        self.start_date = start_date

        self.Eigenkapital_keys = [
            'Einlage',
            'Investment',
            'Investment Sparplan'
            ]
        self.Order_keys = ['ORDER']

        self.KontoIn = Konto('Konto In', self.start_date)
        self.KontoOut = Konto('Konto Out', self.start_date)
        self.KontoSum = Konto('Konto Sum', self.start_date)
        self.DepotIn = Konto('Depot In', self.start_date)
        self.DepotOut = Konto('Depot Out', self.start_date)
        self.DepotSum = Konto('Depot Sum', self.start_date)
        self.CashIn = Konto('Cash In', self.start_date)
        self.CashOut = Konto('Cash Out', self.start_date)
        self.CashSum = Konto('Cash Sum', self.start_date)
        self.OrderIn = Konto('Order In', self.start_date)
        self.OrderOut = Konto('Order Out', self.start_date)
        self.Dividends = Konto('Dividends', self.start_date)

        self.Wertpapiere = []


    def read_data(self, path='.', filetype='xlsx'):
        # read the data from the files and evaluate

        if filetype not in ['csv', 'xlsx']:
            raise Exception("Only file types 'csv' and 'xlsx' supported.")

        # more flexibility
        if not path[-1] == '/' and not path[-1] == '\\':
            path += os.sep

        if not os.path.isdir('./.caching'):
            os.mkdir('.caching')

        files_depot = glob.glob(path + 'Depot*'+filetype)
        files_konto = glob.glob(path + 'Konto*'+filetype)
        df_depot = []
        df_konto = []
        for fd, fk in zip(files_depot, files_konto):
            if filetype == 'csv':
                # csv was such a pain in the ass, I gave up
                raise Exception("File type 'csv' not implemented.")
                dateparse = lambda dates: [dt.datetime.strptime(d, '%d.%m.%Y') for d in dates]
                df_depot.append(pd.read_csv(fd, sep=';', header=0, encoding='ISO-8859-1', parse_dates=['Buchungstag', 'Valuta'], date_parser=dateparse))
                df_konto.append(pd.read_csv(fk, sep=';', header=0, encoding='ISO-8859-1', parse_dates=['Buchungstag', 'Valuta'], date_parser=dateparse))
            if filetype == 'xlsx':
                df_depot.append(pd.read_excel(fd))
                df_konto.append(pd.read_excel(fk))

        self.depot = pd.concat(df_depot, ignore_index=True, sort=False)
        self.konto = pd.concat(df_konto, ignore_index=True, sort=False)

        # make sure konto is sorted for date (Valuta or Buchungsdatum)
        konto_valuta = self.konto['Valuta'].to_numpy()
        konto_info = self.konto['Buchungsinformationen'].to_numpy()
        konto_betrag = self.konto['Betrag'].to_numpy()

        # 'Buchungstag' is more accurate than Valuta
        depot_date = self.depot['Buchungstag'].to_numpy().astype('datetime64[D]')
        # depot_date = depot['Valuta'].to_numpy()
        depot_bezeichnung = self.depot['Bezeichnung'].to_numpy()
        depot_isin = self.depot['ISIN'].to_numpy()
        depot_nominal = self.depot['Nominal (Stk.)'].to_numpy()
        depot_betrag = self.depot['Betrag'].to_numpy()
        depot_kurs = self.depot['Kurs'].to_numpy()
        depot_info = self.depot['Buchungsinformation'].to_numpy()


        # iteration for depot
        for i in range(len(self.depot)):
            # fields from table
            date = depot_date[i]
            info = depot_info[i]
            ISIN = depot_isin[i]
            nominal = depot_nominal[i]
            value_netto = depot_betrag[i] # value without charges
            # value_brutto = depot_betrag[i] # value with charges, money you spend, ToDo
            price = depot_kurs[i]
            name = depot_bezeichnung[i]

            if 'Ausführung' in info:
                if 'Kauf' in info:
                    self.DepotIn.add(date, value_netto)
                if 'Verkauf' in info:
                    self.DepotOut.add(date, value_netto)

                not_in_Wertpapiere = True
                for w in self.Wertpapiere:
                    if w.isin == ISIN:
                        not_in_Wertpapiere = False
                        w.add(date, value_netto, nominal, price)
                if not_in_Wertpapiere:
                    w = Wertpapier(ISIN, name, self.start_date)
                    w.add(date, value_netto, nominal, price)
                    self.Wertpapiere.append(w)


            if 'Split' in info:
                if value_netto > 0: # split appears twice
                    not_in_Wertpapiere = True
                    x = info.split(' ')
                    for y in x:
                        if ':' in y:
                            a, b = y.split(':')
                            split = float(a) / float(b)

                    for w in self.Wertpapiere:
                        if w.isin == ISIN:
                            w.split(split)


            if 'Thesaurierung' in info:
                pass # no action


        # iteration for konto
        for i in range(len(konto_valuta)):
            # fields from table
            date = konto_valuta[i]
            buchungsinfo = konto_info[i]
            value_konto = konto_betrag[i]

            # Konto In/Out/Sum
            self.KontoSum.add(date, value_konto)
            if value_konto > 0:
                self.KontoIn.add(date, value_konto)
            if value_konto < 0:
                self.KontoOut.add(date, value_konto)

            # Cash In and Out
            if any(key in buchungsinfo for key in self.Eigenkapital_keys):
                self.CashIn.add(date, value_konto)
            if 'Flatex Auszahlung' in buchungsinfo:
                self.CashOut.add(date, value_konto)

            # Order Fees and Taxes
            if any(key in buchungsinfo for key in self.Order_keys):
                if 'Kauf' in buchungsinfo: # or value_konto < 0
                    self.OrderIn.add(date, value_konto)
                if 'Verkauf' in buchungsinfo: # or value_konto > 0
                    self.OrderOut.add(date, value_konto)

            if 'Dividenden' in buchungsinfo:
                self.Dividends.add(date, value_konto)

        for w in self.Wertpapiere:
            w.time_update()

        self.DepotSum.addWertpapiere(self.Wertpapiere)
        self.CashSum = self.CashOut + self.CashIn
        self.FeesTaxes = (self.OrderOut - self.OrderIn) - (self.DepotIn - self.DepotOut)
        self.FeesTaxes.name = 'Fees and Taxes'
        self.Portfolio = self.KontoSum + self.DepotSum
        self.Portfolio.name = 'Portfolio'


    def plot_konten(self):
        # plot all 'Konten' with interactive mode

        plt.figure(figsize=FIGSIZE)
        self.KontoIn.plot(True)
        self.KontoOut.plot(True)
        self.KontoSum.plot(True)
        self.DepotIn.plot(True)
        self.DepotOut.plot(True)
        self.DepotSum.plot(True)
        self.CashIn.plot(True)
        self.CashOut.plot(True)
        self.CashSum.plot(True)
        self.OrderIn.plot(True)
        self.OrderOut.plot(True)
        self.Dividends.plot(True)
        self.FeesTaxes.plot(True)
        self.Portfolio.plot(True)
        plt.legend()
        plt.grid()
        self.leg = InteractiveLegend()
        plt.tight_layout()


    def plot_stocks(self, relative=True):
        # plot all stock data abs/rel values with interative mode

        plt.figure(figsize=FIGSIZE)
        for i in range(len(self.Wertpapiere)):
            w = self.Wertpapiere[i]
            # w.time_update()
            if len(w.time) == 0:
                continue
            Label = '{} {:0.2f}€ ({})'.format(w.name, w.Absolut[-1], i)
            plt.plot(w.time, w.Absolut, label=Label)
        plt.legend()
        plt.grid()
        self.leg1 = InteractiveLegend()
        plt.tight_layout()

        plt.figure(figsize=FIGSIZE)
        for i in range(len(self.Wertpapiere)):
            w = self.Wertpapiere[i]
            if len(w.time) == 0:
                continue
            Label = '{} {:0.2f}€ ({})'.format(w.name, w.Relativ[-1], i)
            plt.plot(w.time, w.Relativ, label=Label)
        plt.legend()
        plt.grid()
        self.leg2 = InteractiveLegend()
        plt.tight_layout()


    def plot_price_history(self):
        plt.figure(figsize=FIGSIZE)
        for i in range(len(self.Wertpapiere)):
            w = self.Wertpapiere[i]
            if len(w.time) == 0:
                continue
            Label = '{} {:0.2f}€ ({})'.format(w.name, w.price_history[-1], i)
            plt.plot(w.time, w.price_history, label=Label)
        plt.legend()
        plt.grid()
        self.leg3 = InteractiveLegend()
        plt.tight_layout()

    def select(self, name):
        # select a stock based by name or isin (str or list)
        # return info about buys/sells/number stocks
        pass


    # single analysis of stocks and other stuff on demand


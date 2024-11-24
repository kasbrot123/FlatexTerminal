"""

Kontoumsätze für genaue Abrechnung
    -> Gebühren und Steuer ist bereits abgezogen etc.
    -> Das sind die Wichtigen Events

Depotumsätze
    -> sagen mir wiehoch der Kurs war
    -> Lookup wieviel geld ich vor Steuern/Gebühr bekomme
    -> Berechnung von realem Gewinn
    -> 



1. Import Excel/csv table
2. Iterate over every entry







"""

import pandas as pd
from matplotlib import pyplot as plt



class Konto():
    def __init__(self, name):
        self.name = name
        self.dates = []
        self.values = []
        self.value = 0

    def add(self, date, value):
        self.value += value
        self.dates.append(date)
        self.values.append(self.value)

    def plot(self):
        if len(self.values) != 0:
            plt.plot(self.dates, self.values, 'o--', label='{} ({:0.2f} €)'.format(self.name, self.values[-1]))

    # def __add__(self, other):
    #
    #     # some test if other is the same object
    #     # ...
    #
    #     self.values = 
    #     Sum = Konto('sum')
    #     Sum.values 




class Wertpapier():

    def __init__(self, ID, name):

        self.ID = ID
        self.name = name

        self.date = []
        self.konto = []
        self.depot = []
        self.kurs = []
        # self.kurs_mean = []
        self.stueck = []
        self.gewinn = []
        self.gebuehr = []

        self.n_stocks = 0
        self.mean_price = 0

    def buy(self, date, value_konto, value_depot, number, kurs):
        self.date.append(date)
        self.konto.append(value_konto)
        self.depot.append(value_depot)
        self.stueck.append(number)
        self.kurs.append(kurs)
        self.gewinn.append(0)
        self.gebuehr.append(-value_konto-value_depot)

        self.mean_price = (self.n_stocks * self.mean_price + number * kurs)/(self.n_stocks + number)
        self.n_stocks += number



    def sell(self, date, value_konto, value_depot, number, kurs):
        self.date.append(date)
        self.konto.append(value_konto)
        self.depot.append(value_depot)
        self.stueck.append(number)
        self.kurs.append(kurs)
        self.gebuehr.append(-value_konto-value_depot)

        self.gewinn.append(value_konto-number*self.mean_price)
        self.n_stocks -= number




depot_path = './Depotumsätze (1).xlsx'
konto_path = './Kontoumsätze (1).xlsx'


depot = pd.read_excel(depot_path)
konto = pd.read_excel(konto_path)

# make sure konto is sorted for date (Valuta or Buchungsdatum)
konto_valuta = konto['Valuta'].to_list()
konto_info = konto['Buchungsinformationen'].to_list()
konto_betrag = konto['Betrag'].to_list()


depot_bezeichnung = depot['Bezeichnung'].to_list()
depot_nominal = depot['Nominal (Stk.)'].to_list()
depot_betrag = depot['Betrag'].to_list()
depot_kurs = depot['Kurs'].to_list()
depot_info = depot['Buchungsinformation'].to_list()
depot_isin = depot['ISIN'].to_list()


# def return_index(key, array):
#     return array.index(key)


Depotkonto = Konto('Depot')
Einlagenkonto = Konto('Einlage')
Gesamtkonto = Konto('Gesamt')
OhneEinlagen = Konto('Ohne Einlagen')



Wertpapiere = []



for i in range(len(konto_valuta)):
    date = konto_valuta[i]
    buchungsinfo = konto_info[i]
    value_konto = konto_betrag[i]


    if 'Ausführung' in buchungsinfo:
        # index = return_index(konto_info[i], depot_info)
        index = depot_info.index(konto_info[i])
        value_depot = depot_betrag[index]
        number = abs(depot_nominal[index])
        kurs = depot_kurs[index]
        ISIN = depot_isin[index]
        name = depot_bezeichnung[index]

        # print(value_konto, value_depot)

         # = depot_isin[index]


        Einlagenkonto.add(date, value_konto)
        Depotkonto.add(date, value_depot)
        Gesamtkonto.add(date, value_konto+value_depot)
        OhneEinlagen.add(date, value_konto)


        not_in_Wertpapiere = True
        for w in Wertpapiere:
            if w.ID == ISIN:
                not_in_Wertpapiere = False
                if value_konto < 0:
                    # print('bought more')
                    w.buy(date, value_konto, value_depot, number, kurs)
                if value_konto > 0:
                    # print('sold')
                    w.sell(date, value_konto, value_depot, number, kurs)


        if not_in_Wertpapiere:
            # print('added wertpapier')
            wertpapier = Wertpapier(ISIN, name)
            if value_konto < 0:
                wertpapier.buy(date, value_konto, value_depot, number, kurs)
                Wertpapiere.append(wertpapier)
            else:
                print("error, something's wrong")
    # else:
    #     pass
        # print('not a order')

    # if i == 1:
    #     break

    else:
        # this means everything else than 'Ausführung' is a payment to or from the 'Einlagenkonto' and does not influence the ''
        Einlagenkonto.add(date, value_konto)
        Gesamtkonto.add(date, value_konto)
        if any(note in buchungsinfo for note in ['Einlage', 'Auszahlung', 'Investment']):
            pass
        else:
            OhneEinlagen.add(date, value_konto)


Stock_names = [w.name for w in Wertpapiere]

for w in Wertpapiere:
    if sum(w.gewinn) == 0:
        continue
    print('{}: {:0.2f}€'.format(w.name,sum(w.gewinn)))



Gewinn = sum([sum(w.gewinn) for w in Wertpapiere])
print('Gewinn Aktien: {:0.2f}€'.format(Gewinn))


fig = plt.figure()
Einlagenkonto.plot()
Depotkonto.plot()
Gesamtkonto.plot()
OhneEinlagen.plot()
plt.grid()
plt.legend()
plt.xlabel('time')
plt.ylabel('Money in €')

plt.show()



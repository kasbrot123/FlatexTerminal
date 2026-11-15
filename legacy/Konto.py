import numpy as np
from matplotlib import pyplot as plt




class Konto():
    def __init__(self, name, start_date):
        self.name = name
        self.dates = []
        self.values = []
        self.value = 0
        self.start_date = start_date

        start = np.datetime64(self.start_date, 'D')
        end = np.datetime64('today', 'D') + np.timedelta64(1, 'D') # because arange

        self.time = np.arange(start, end, np.timedelta64(1, 'D'))
        self.t_values = np.zeros(len(self.time))
        self.tsum_values = np.zeros(len(self.time))


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

    def addWertpapiere(self, Wertpapiere):
        # quick and dirty
        self.tsum_values = 0
        for w in Wertpapiere:
            if len(w.Absolut) == 0:
                continue
            self.tsum_values += w.Absolut



    def plot(self, everyday=False):
        if everyday:
            plt.plot(self.time, self.tsum_values, '-', label='{} {:0.2f} €'.format(self.name, self.tsum_values[-1]))
        else:
            values_cumsum = np.cumsum(self.values)
            plt.plot(self.dates, values_cumsum, 'o--', label='{} {:0.2f} €'.format(self.name, values_cumsum[-1]))



    def __add__(self, Add):

        if not isinstance(Add, Konto):
            raise Exception('Addition only possible between Konto classes')

        NewObject = Konto('('+self.name + ' + ' +Add.name+')', self.start_date)
        # NewObject.t_values = self.t_values + Add.t_values
        # NewObject.tsum_values = np.cumsum(NewObject.t_values)
        NewObject.tsum_values = self.tsum_values + Add.tsum_values

        # dates and values not really necessary
        new_dates = list(self.dates) + list(Add.dates) # list() -> copy
        new_values = list(self.values) + list(Add.values)
        NewObject.value = sum(new_values)

        # one could also just call .add function for each pair
        NewObject.dates = [d for d, _ in sorted(zip(new_dates, new_values))]
        NewObject.values = [v for _, v in sorted(zip(new_dates, new_values))]

        return NewObject

    def __sub__(self, Sub):

        if not isinstance(Sub, Konto):
            raise Exception('Subtraction only possible between Konto classes')

        NewObject = Konto('('+self.name + ' - ' +Sub.name+')', self.start_date)
        # NewObject.t_values = self.t_values - Sub.t_values
        # NewObject.tsum_values = np.cumsum(NewObject.t_values)
        NewObject.tsum_values = self.tsum_values - Sub.tsum_values

        # dates and values not really necessary
        new_dates = list(self.dates) + list(Sub.dates) # list() -> copy
        new_values = list(self.values) + list(Sub.values)
        NewObject.value = sum(new_values)

        # one could also just call .add function for each pair
        NewObject.dates = [d for d, _ in sorted(zip(new_dates, new_values))]
        NewObject.values = [v for _, v in sorted(zip(new_dates, new_values))]

        return NewObject

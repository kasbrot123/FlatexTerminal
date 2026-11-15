"""
ToDo

    High Priority:
        - write Readme
        - Interactive Legend not working when loading many stocks 

    Low Priority:
        - START_PORTFOLIO is given by files (but you could choose a earlier date)
        - Vielleicht die Aktien bei komplettem Verkauf trennen sodass neuer eff. Preis entsteht
        - Englisch/Deutsch -> einheitlich
        - faster solution when downloading all at once with 'Tickers' ?

"""

from matplotlib import pyplot as plt
from Terminal import Terminal



####################################
# Global Definitions 

PATH = './Flatex_Export'
START_PORTFOLIO = '2023-05-01'



################################################################################

if __name__ == '__main__':

    terminal = Terminal(START_PORTFOLIO)
    terminal.read_data(path=PATH)
    terminal.plot_stocks()
    terminal.plot_price_history()
    terminal.plot_konten()

    plt.show()



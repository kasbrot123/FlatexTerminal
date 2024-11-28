"""
ToDo

    High Priority:
        - write Readme
        - Interactive Legend not working when loading many stocks 

    Low Priority:
        - Vielleicht die Aktien bei komplettem Verkauf trennen sodass neuer eff. Preis entsteht
        - Englisch/Deutsch -> einheitlich
        - faster solution when downloading all at once with 'Tickers' ?
        - exception in loop correct_times_prices


"""

from matplotlib import pyplot as plt
from Terminal import Terminal



####################################
# Global Definitions 

PATH = './Flatex_Export'

START_PORTFOLIO = '2023-05-01'
TODAY = '2024-11-28'



################################################################################

if __name__ == '__main__':

    terminal = Terminal(START_PORTFOLIO)
    terminal.read_data(path=PATH)
    terminal.plot_stocks()
    terminal.plot_price_history()
    terminal.plot_konten()

    plt.show()



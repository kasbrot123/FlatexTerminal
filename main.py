"""

ToDo

    High Priority:
        - classes in different files, rename files
        - add example with example data
        - wertpapiere time_update ändern
        - write Readme
        - only print warnings not all stocks

    Low Priority:
        - Vielleicht die Aktien bei komplettem Verkauf trennen sodass neuer eff. Preis entsteht
        - tickerlist reload module
        - Englisch/Deutsch -> einheitlich
        - faster solution when downloading all at once with 'Tickers' ?
        - Interactive Legend not working when loading many stocks 
        - exception in loop correct_times_prices


Terminal.py
Konto.py
Wertpapier.py
InteractiveLegend.py
functions.py
settings.py
main.py / flatex_terminal.py





"""


# global modules
# import pandas as pd
# import numpy as np
# import yfinance as yf
# import time
# import os
# import glob
# import datetime as dt
# import requests
# import random
# from TickerList import TickerList # reload

import logging
from matplotlib import pyplot as plt


from Terminal import Terminal
from settings import PATH


####################################
# Global Definitions 


logger = logging.getLogger('yfinance')
logger.disabled = True
logger.propagate = False


################################################################################



if __name__ == '__main__':

    terminal = Terminal()
    terminal.read_data(path=PATH)
    terminal.plot_stocks()
    terminal.plot_price_history()
    terminal.plot_konten()

    plt.show()



# Flatex Terminal

This repository contains Python code to visualize the assets of your
[Flatex](https://www.flatex.at) depot in a more versatile manner.

## How to use

### Export

To evaluate your stock data, export all data from Flatex.

- `Depotumsätze.xlsx`
- `Kontoumsätze.xlsx`

- (`Orders-XXXXXXXX-XXXXXXXX.xlsx` is not needed)

You can specify an individual time range and you may need to export multiple
files since Flatex does not include all the data in your interval. It is fine
to save your files with date, just make sure to accordingly name your files
starting with `Depot*.xlsx` and `Konto*.xlsx` (Example:
`Depotumsätze_2024_1.xlsx`, `Depotumsätze_2024_2.xlsx`, ...). Put all files in
a folder and specify the path in the python script.

### Run `main.py`

To evaluate your stock data you first have to define your file path and your
start date. You can set the date according to your depot data but you can also
choose a previous date. Make sure to select a date before the first entry from
Flatex.

```python
PATH = './Flatex_Export'
START_PORTFOLIO = '2023-05-01'
```

When running the script for the first time it will download all the stock data
using the package `yfinance`. This can take a while since the download includes
`sleep()` calls to prevent and IP block. The data is saved in `.cache` and used
then instead of downloading again.


### Results

The script shows the stock data in absolute and relative values and the stock
price over time. In addition the script uses the data from `Kontoumsätze` to
calculate the balance of your portfolio as well as other quantities like cash
flow, fees and taxes dividends etc. (see below). The plots work interactive and
one can hide/show the line by clicking on the legend name. At the time a basic
visualization of the depot activities for a Flatex depot is implemented.

The code should work with most of the stocks from Flatex. There might be some
problems finding the right ticker but you can search the stock on [yahoo
finance](https://finance.yahoo.com) and manually define the ticker by yourself.


## Python classes

### `Terminal.py`

This is the main class and holds all information and functionalities to analyze.
The idea is to calculate, plot, analyze all information via this class.

### `Konto.py`

This class is super usefull to collect all entries with a certain condition. It
lets you analyze the cash flow, the "Konto(-Saldo)", the depot value, fee and
taxes, and so on. Every object holds a time vector with its value vector so you
can add different objects to get new quantities like the sum or a relative
quantity. 

These are the predefined objects of the class `Konto`:

    Tracking:
        - Depot Incoming (DepotIn)
        - Depot Outgoing (DepotOut)
        - Konto Incoming (KontoIn)
        - Konto Outgoing (KontoOut)
        - Cash Incoming (CashIn)
        - Cash Outgoing (CashOut)
        - Dividends after tax (Dividends)

    Calculated:
        KontoSaldo = 
            Konto Incoming - Konto Outgoing
            (KontoSum)

        Depot Value = 
            Summe{ Value of all assets/stocks }
            (DepotSum)

        Fees and Taxes = 
            (Konto Incoming - Konto Outgoing) - (Depot Outgoing - Depot Incoming)
            (FeesTaxes)

        Portfolio in Total = 
            KontoSaldo + Depot Value
            (Portfolio)

### `Wertpapiere.py`

This class holds every entry of a stock/asset of the same ISIN. Important
fields like value, price, nominals are stored and then a time vector is
calculated to compare it over time with other stocks.



## Current Status

~~**This repository is currently in development and highly unfinished.**~~

~~The code structure is still not optimized and there are a lot of debugging
features in the code. A clean up is done afterwards when the main features are
implemented.~~

**Latest Major Changes**

*Update 2024-11-28*: Restructured files and put classes and functions in own files

*Update 2024-11-26*: Stable Version with multiple file support and ETFs history

*Update 2024-11-24*: First Version with Terminal class



# Flatex Terminal

Python code for visualizing the assets of your flatex depot.

**Latest Version:** `new2.py`


## Current Status

**This repository is currently in development and highly unfinished.**

The code structure is still not optimized and there are a lot of debugging features in the code. A clean up is done afterwards when the main features are implemented. 


*Update 2024-11-26*: Stable Version with multiple file support and ETFs history

*Update 2024-11-24*: First Version with Terminal class


## To write

- Terminal class (and functionalities)
- Konto class (and functionalities)
- Wertpapier class (and functionalities)
- Only using `Depotumsätze.xlsx` and `Kontoumsätze.xlsx` (not `Orders-XXXXXXXX-XXXXXXXX.xlsx`)
- Flatex does not export all data when using individual time frame (only with Kontoumsätze)
- Explanation of different types of 'Konten'


### Explanation of `Konten`





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

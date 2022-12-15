# tostools
Python3 Command-line tól til að auðvelda notkun með https://tos.vedur.is

# Uppsetning
Eingöngu með Python3 (3.6+)

"Clone:a" þetta repo

Nauðsynleg python-library:
* tabulate : pip3 install tabulate

# Notkun
`python3 tos.py --help`

# Notkunardæmi
## Leit að stöð
 * `tos.py vadla`
 * `tos.py ada`
 * `tos.py aust`
 * `tos.py V89`
 * `tos.py reitr fagho`

## Leit að tæki með raðnúmeri (-s)
 * `tos.py -s 182820302`
 * `tos.py -s A086`

## Leit að tæki með Galvos-númeri (G)
 * `tos.py -G 10001` 


## Snið á úttaki (-o)
 * `tos.py vadla -o pretty` (sjálfgefið)
 * `tos.py vadla -o table`
 * `tos.py vadla -o json`
 * `tos.py -s A086 -o table`
 
## Snið á töflu (-t)
Sjá öll studd töflusnið á https://pypi.org/project/tabulate/
 * `tos.py vadla -t simple` (sjálfgefið)
 * `tos.py vadla -t plain`
 * `tos.py vadla -t github`
 
 
## Snið á úttaki (-o) og töflusnið (-t)
 * `tos.py vadla -o table -t github`
  
## Takmörkun við óðal (-D)
 * `python3 tos.py ada -D geophysical`


# TODO
* Saga á breytum og tækjum
* Hafa default config, sem hægt overrida á command line
* Stöðvar innan fjarlægðar
* Næstu stöðvar
* PDF

## Hugsanlegar skipanir
* `python tos.py -met 20221`
* `python tos.py -met rauhf -type csv`
* `python tos.py -met rauhf -type json`
* `python tos.py -met rauhf -type json -attributes (location,lon,asdf)`
* `python tos.py -met ALL -type csv -attributes (location,lon,asdf)`
* `tos.py 65454`

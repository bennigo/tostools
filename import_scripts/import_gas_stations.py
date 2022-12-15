#!/usr/bin/python
# coding=utf-8
#
# Project: ToS
# Authors: Tryggvi Hjörvar
# Date: Jul 2016
# 
# Script to import and process gas station data from csv to tos (pg)
#

import json
import requests
from datetime import datetime
import csv




station = {}
station['marker'] = 'hekla'
station['station_type_code'] = 'multigas'
station['name'] = 'Hekla'
station['lat'] = 63.9833
station['lon'] = 19.7000
station['date_from'] = '2013-03-20 00:00:00'

station['items'] = [
    {'item_type':'co2_sensor','date_from':'2013-04-30 00:00:00','date_to':'2013-07-02 00:00:00','attributes':[
        {'serial_number':'3048','date_from':'2013-04-30 00:00:00'},
        {'sensor_sensitivity':'1%','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_min':'5243','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_max':'26214','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'so2_sensor','date_from':'2013-04-30 00:00:00','date_to':'2013-07-02 00:00:00','attributes':[
        {'serial_number':'01. 13557595 128','date_from':'2013-04-30 00:00:00'},
        {'sensor_sensitivity':'0-30 ppm','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_min':'5200','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_max':'12700','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'h2s_sensor','date_from':'2013-04-30 00:00:00','date_to':'2013-07-02 00:00:00','attributes':[
        {'serial_number':'01. 19966817 062','date_from':'2013-04-30 00:00:00'},
        {'sensor_sensitivity':'0-50 ppm','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_min':'5390','date_from':'2013-04-30 00:00:00'},
        {'sensor_range_max':'8700','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2013-04-30 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'ampere_hours':'200','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2013-04-30 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'ampere_hours':'200','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2013-04-30 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'ampere_hours':'200','date_from':'2013-04-30 00:00:00'},
    ]},
    {'item_type':'solar_panel','date_from':'2013-04-30 00:00:00','date_to':'2015-03-15 00:00:00','attributes':[
        {'watts':'100','date_from':'2013-04-30 00:00:00'},
    ]},

    {'item_type':'co2_sensor','date_from':'2013-07-02 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'serial_number':'956','date_from':'2013-07-02 00:00:00'},
        {'sensor_sensitivity':'10%','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_min':'5345','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_max':'26700','date_from':'2013-07-02 00:00:00'},
    ]},
    {'item_type':'so2_sensor','date_from':'2013-07-02 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'serial_number':'01. 19958037 062','date_from':'2013-07-02 00:00:00'},
        {'sensor_sensitivity':'0-200 ppm','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_min':'5200','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_max':'12700','date_from':'2013-07-02 00:00:00'},
    ]},
    {'item_type':'h2s_sensor','date_from':'2013-07-02 00:00:00','date_to':'2014-03-12 00:00:00','attributes':[
        {'serial_number':'01. 19572501 042','date_from':'2013-07-02 00:00:00'},
        {'sensor_sensitivity':'0-50 ppm','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_min':'5380','date_from':'2013-07-02 00:00:00'},
        {'sensor_range_max':'10240','date_from':'2013-07-02 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2014-03-12 00:00:00','attributes':[
        {'ampere_hours':'240','date_from':'2014-03-12 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2014-03-12 00:00:00','attributes':[
        {'ampere_hours':'240','date_from':'2014-03-12 00:00:00'},
    ]},

    {'item_type':'co2_sensor','date_from':'2014-03-12 00:00:00','date_to':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'2668','date_from':'2014-03-12 00:00:00'},
        {'sensor_sensitivity':'10%','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_min':'5360','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_max':'26220','date_from':'2014-03-12 00:00:00'},
    ]},
    {'item_type':'so2_sensor','date_from':'2014-03-12 00:00:00','date_to':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'01.25956212 113','date_from':'2014-03-12 00:00:00'},
        {'sensor_sensitivity':'0-50 ppm','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_min':'5335','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_max':'26420','date_from':'2014-03-12 00:00:00'},
    ]},
    {'item_type':'h2s_sensor','date_from':'2014-03-12 00:00:00','date_to':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'01.19572480 042','date_from':'2014-03-12 00:00:00'},
        {'sensor_sensitivity':'0-50 ppm','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_min':'5243','date_from':'2014-03-12 00:00:00'},
        {'sensor_range_max':'26100','date_from':'2014-03-12 00:00:00'},
    ]},
    {'item_type':'battery','date_from':'2015-03-15 00:00:00','attributes':[
        {'ampere_hours':'240','date_from':'2015-03-15 00:00:00'},
    ]},
    {'item_type':'solar_panel','date_from':'2015-03-15 00:00:00','attributes':[
        {'watts':'140','date_from':'2015-03-15 00:00:00'},
    ]},
    {'item_type':'solar_panel','date_from':'2015-03-15 00:00:00','attributes':[
        {'watts':'140','date_from':'2015-03-15 00:00:00'},
    ]},

    {'item_type':'co2_sensor','date_from':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'Current Hekla','date_from':'2015-03-15 00:00:00'},
        {'sensor_sensitivity':'10%','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_min':'5243','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_max':'25500','date_from':'2015-03-15 00:00:00'},
    ]},
    {'item_type':'so2_sensor','date_from':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'Current Hekla','date_from':'2015-03-15 00:00:00'},
        {'sensor_sensitivity':'0-200 ppm','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_min':'5300','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_max':'10000','date_from':'2015-03-15 00:00:00'},
    ]},
    {'item_type':'co2_sensor','date_from':'2015-03-15 00:00:00','attributes':[
        {'serial_number':'Current Hekla','date_from':'2015-03-15 00:00:00'},
        {'sensor_sensitivity':'0-50 ppm','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_min':'5320','date_from':'2015-03-15 00:00:00'},
        {'sensor_range_max':'23400','date_from':'2015-03-15 00:00:00'},
    ]},

]

#print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text


station = {}
station['marker'] = 'krvik'
station['station_type_code'] = 'multigas'
station['name'] = 'Krýsuvík'
station['date_from'] = '2013-04-26 00:00:00'
station['lat'] = 63.895853
station['lon'] = 22.054928
#print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text


station = {}
station['marker'] = 'rngb'
station['station_type_code'] = 'dissolvedco2'
station['name'] = 'Rangárbotnar'
station['date_from'] = '2015-07-27 00:00:00'
station['lat'] = 63.862454
station['lon'] = 19.539970
print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text


station = {}
station['marker'] = 'sels'
station['station_type_code'] = 'dissolvedco2'
station['name'] = 'Selsund'
station['date_from'] = '2014-07-09 00:00:00'
station['lat'] = 63.941111
station['lon'] = 19.971956
print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text


station = {}
station['marker'] = 'holu'
station['station_type_code'] = 'multigas'
station['name'] = 'Holuhraun'
station['date_from'] = '2015-02-16 00:00:00'
station['lat'] = 64.849459
station['lon'] = 16.829874
print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text


station = {}
station['marker'] = 'port'
station['station_type_code'] = 'multigas'
station['name'] = 'Portable'
station['date_from'] = '2014-07-11 00:00:00'
station['lat'] = 64.127618
station['lon'] = 21.904040
print json.dumps(station)
r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station))
print r.text

#!/usr/bin/python
# coding=utf-8
#
# Project: ToS
# Authors: Tryggvi Hjörvar
# Date: Jul 2016
# 
# Script to import and process met station data from access_taeki (pg) to gps/tos (pg)
#

import sys
import logging
import psycopg2
from psycopg2 import extras
import datetime
from datetime import datetime
import requests
import json



#----JSONDateEncoder----
class JSONDateEncoder(json.JSONEncoder):
    """ Custom JSON encoder to handle datetime objects
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            #return int(mktime(obj.timetuple()))
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return json.JSONEncoder.default(self, obj)



marker = 'kalfh'

#print 'Importing {}'.format(marker,)

try:
    conn_acc = psycopg2.connect(dbname="access_taeki", user="", password="", host="localhost")

except:
    print "Could not connect to database"
    sys.exit()

#cur_acc = conn_acc.cursor()  
cur_acc = conn_acc.cursor(cursor_factory=psycopg2.extras.DictCursor)

cur_acc.execute("""
              select *
              from stod s
              where s.skst=%s
            """, (marker,) )
result = cur_acc.fetchone()
#print result

#print str(result['stod'])
#print repr(result['nafn'])

#{"marker":"TEST",
#"name": "TEST",
#    "items":[{"item_type":"antenna","serial_number":"test","date_from":"2015-06-30 00:00:00","attributes":[{"description":"testdesc1","date_from":"2015-01-01 00:00:00","date_to":"2016-05-05 00:00:00"}]},
#            {"item_type":"radome","serial_number":"test2","attributes":[{"description":"testdesc2","date_from":"2015-05-05 00:00:00","date_to":"2016-05-05 00:00:00"}]}]
#}

map_item_type = {
    'Datalogger':'datalogger',
    'Tengibretti':'connector_board',
    '12 V aflgjafi':'power_pack_12v',
    'Merkjabreytir':'analog_digital_converter',
    'Rafeindaloftvog':'barometer_digital',
    'Raka- og hitamælir':'humidity_and_thermometer',
    'Platínuhitamælir - PT100':'thermometer_platinum',
    'Vindhraða- og vindáttarmælir - skrúfumælir':'anemometer_vane',
    }

station = { 'marker':result['skst'], 
            'name':result['nafn'], 
            'imo_number':str(result['stod'])}
#print station

result = cur_acc.execute("""
              select t.upphaf as upphaf, t.endir, t.radnr, tg.lysing as gerd
              from stod s, taeki_stod ts, taeki t, taeki_flokkur tf, taeki_gerd tg, taeki_tegund tt
              where ts.stod=s.stod
              and ts.taeki=t.taeki
              and t.flokkur=tf.flokkur
              and t.gerd=tg.gerd
              and t.tegund=tt.tegund
              and s.skst=%s
            """, (marker,) )
items = []
for record in cur_acc:
    item = {'item_type':map_item_type[record['gerd']], 'serial_number':record['radnr'], 'attributes':[{'serial_number':record['radnr']}]}
    if record['upphaf']:
        item['date_from'] = record['upphaf']
    if record['endir']:
        item['date_to'] = record['endir']
    items.append(item)
station['items'] = items
#conn.commit()

#print json.dumps(station, cls=JSONDateEncoder)
r = requests.post('https://tos-zato.dev.vedur.is/tos/v1/station', data = json.dumps(station, cls=JSONDateEncoder))
print r.text
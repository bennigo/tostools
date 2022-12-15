#!/usr/bin/python
# coding=utf-8
#
# Project: ToS
# Authors: Tryggvi Hjörvar
# Date: Jul 2016
# 
# Script to import and process met item data not attached to any station from access_taeki (pg) to tos (pg)
#

import sys
import logging
import psycopg2
from psycopg2 import extras
import datetime
from datetime import datetime
import requests
import json
import ibm_db


#----JSONDateEncoder----
class JSONDateEncoder(json.JSONEncoder):
    """ Custom JSON encoder to handle datetime objects
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            #return int(mktime(obj.timetuple()))
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        #elif isinstance(obj, Decimal):
        #    return float(obj)
        return json.JSONEncoder.default(self, obj)

 
map_item_type = {
    'Datalogger': 'datalogger',
    'Tengibretti': 'connector_board',
    '12 V aflgjafi': 'power_pack_12v',
    'Merkjabreytir': 'analog_digital_converter',
    'Coax Multidrop Interface': 'coax_multidrop_interface',
    'RS-485 Multidrop Interface': 'rs485_multidrop_interface',
    'Hleðslutæki': 'charger',
    'Vindmælaaflgjafi': 'anemometer_power_pack',
    'Solar charge controller': 'solar_charge_controller',
    'Gamma Tracer XL': 'gamma_radiation_detector',
    'Net Radiometer': 'radiometer',
    'Pyranometer': 'pyranometer',
    'Pyrgeometer': 'pyrgeometer',    
    'Sólskinsstundamælir': 'sunshine_detector',
    'Laser endurvarpi (backscatter)': 'laser_backscatter_sensor',
    'Forward scatter': 'forwardscatter_sensor',
    'UV-mælir': 'ultraviolet_radiation_meter',
    'Últrasónískur snjódýptarmælir': 'snowdepth_meter_ultrasonic',
    'Ratsjá snjódýptarmælir': 'snowdepth_meter_radar',
    'Fastlínumótald': 'modem_landline',
    'GSM mótald': 'modem_gsm',
    'Radiomótald': 'modem_radio',
    'Rafeindaloftvog': 'barometer_digital',
    'Mekanísk loftvog': 'barometer_mechanical',
    'Kvikasilfursloftvog': 'barometer_mercury',
    'Hitariti': 'thermometer_continuous',
    'Þrýstiriti': 'pressure_gauge_continuous',
    'Þrýstinemi': 'pressure_gauge',
    'Raka- og hitamælir': 'humidity_and_thermometer',
    'Hámarksmælir - Hg': 'thermometer_maximum_mercury',
    'Lágmarksmælir - Spritt': 'thermometer_minimum_spiritus',    
    'Platínuhitamælir - PT100': 'thermometer_platinum',
    'Sjávarhitamælir - Hg': 'thermometer_ocean_mercury',
    'Jarðvegshitamælir - Hg': 'thermometer_underground_mercury',
    'Thermistor': 'thermometer_thermistor',
    'Vindhraða- og vindáttarmælir - skrúfumælir': 'anemometer_vane',
    'Vindhraða- og vindáttarmælir - sónískur': 'anemometer_ultrasonic',
    'Vindhraða- og vindáttarmælir - skálamælir': 'anemometer_cup',
    'Vindhraða- og vindáttarmælir - thermiskur': 'anemometer_thermal',
    'Vindhraði - skálamælir': 'anemometer_windspeed_cup',
    'Vindáttarmælir': 'anemometer_direction',
    'Vindáttarskífa': 'anemometer_direction_dial',
    'Vindhraðaskífa': 'anemometer_windspeed_dial',
    'Skrifari':'writer',
    'Panel':'panel',
    'Hitamælir - Hg': 'thermometer_mercury',
    'Vippumælir': 'precipitation_gauge_tipping_bucket',
    'Vigtuð fata með víbrandi vír': 'precipitation_gauge_vibrating_wire',
    'Úrkomuriti með flotholti': 'precipitation_gauge_continuous_float',    
    'GPS staðsetningatæki': 'gps',
    'Eldingaáttarmælir': 'lightning_detector_direction', 
    'Prófun_T_Tv':'thermometer_comparison_t_tv',
    'Prófun_T0 (kvikasilfursmæli -1 ... 1°C)':'thermometer_comparison_mercury_1_degree_c',
    'Prófun_p':'barometer_comparison_p',
    'Prófun_T (kvikasilfursmæli)':'thermometer_comparison_mercury_t',
    }


#Connect to access_taeki (pg)
try:
    conn_acc = psycopg2.connect(dbname="access_taeki", user="", password="", host="localhost")
except:
    print "Could not connect to database"
    sys.exit()
cur_acc = conn_acc.cursor(cursor_factory=psycopg2.extras.DictCursor)



#Items present in Access, without any station
#Get items from access_taeki (pg)
acc_result = cur_acc.execute("""
                            select t.upphaf as taeki_upphaf, t.endir as taeki_endir, t.radnr, tg.lysing as gerd, t.lysing as taeki_comment
                            from taeki t
                            join taeki_flokkur tf
                              using(flokkur)
                            join taeki_gerd tg
                              using(gerd)
                            join taeki_tegund tt
                              using(tegund)
                            left outer join taeki_stod ts
                              using (taeki)
                            where ts.taeki is null
                            and (tegund,radnr) not in (select tegund,radnr
                            from taeki
                            group by tegund,radnr
                            having count(1)>1)
                            and radnr not in ('1000','0117-01','4806','4779','22257','6890/87','2','3516/96','7813319','95/03','84/03','983/01','X2310020')
                            """)

for record in cur_acc:
    item = {'item_type':map_item_type[record['gerd']], 'serial_number':record['radnr'], 'attributes':[{'serial_number':record['radnr']}]}
    
    if record['taeki_comment']:
        attribute = {'comment' : record['taeki_comment']}
        item['attributes'].append(attribute)

    if record['taeki_upphaf']:
        item['attributes'].append({'date_start' : record['taeki_upphaf']})
    if record['taeki_endir']:
        item['attributes'].append({'date_end' : record['taeki_endir']})

    #print json.dumps(item, cls=JSONDateEncoder)
#    r = requests.post('https://tos-zato.dev.vedur.is/tos/item', data = json.dumps(item, cls=JSONDateEncoder))
#    print r.text



#Close
conn_acc.close()

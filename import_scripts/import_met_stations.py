#!/usr/bin/python
# coding=utf-8
#
# Project: ToS
# Authors: Tryggvi Hjörvar
# Date: Jul 2016
# 
# Script to import and process met station data from access_taeki (pg) to tos (pg)
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



#Connect to DB2
try:
    conn_db2 = ibm_db.connect("DATABASE=stafli;HOSTNAME=stafli.db.vedur.is;PORT=50010;PROTOCOL=TCPIP;UID=;PWD=;", "", "")
except:
    logging.critical("Could not connect to database stafli")
    print "Could not connect to database stafli"
    sys.exit()

#select s.skst, CAST( s.stod AS int) as stod, s.nafn, s.teg, s.eig, s.breidd_y, s.lengd_x, s.h_stod, s.aths, CAST( s.stod_wmo AS int) as stod_wmo, sp.spasv as spasv_nr, sp.heiti as spasv_heiti
sql = """select s.*, sp.spasv as spasv_nr, sp.heiti as spasv_heiti
        from sta.stod s
        left outer join sta.spa_svaedi sp
          on s.spasv=sp.spasv
        --where stod in (3470,1481,6935,7078)
        order by stod
    """
stmt = ibm_db.exec_immediate(conn_db2, sql)

db2result = ibm_db.fetch_assoc(stmt)
while( db2result ):
    marker = db2result['SKST']

    #Get station from access_taeki (pg)
    cur_acc.execute("""
                  select *
                  from stod s
                  where s.skst=%s
                """, (marker,) )
    acc_result = cur_acc.fetchone()

    #Create station dict
    #Handle duplicate markers
    if db2result['STOD'] == 4:
        marker='rvks'
    elif db2result['STOD'] == 31484:
        marker='sansk-1'
    else:
        marker = db2result['SKST']
    station = { 'marker': marker, 
                'name': db2result['NAFN'], 
                'station_type_code': db2result['TEG'], 
                'agency': db2result['EIG'],
                'lat': db2result['BREIDD_Y'],
                'lon': db2result['LENGD_X'],
                'altitude': db2result['H_STOD']
                }

    #Attributes
    station_attributes = []
    station_attributes.append({'imo_number': str(db2result['STOD'])})
    if db2result['STOD_WMO']:
        station_attributes.append({'wmo_number': str(db2result['STOD_WMO'])})
    if db2result['UPPHAF']:
        station_attributes.append({'date_start': str(db2result['UPPHAF'])})
    if db2result['ENDIR']:
        station_attributes.append({'date_end': str(db2result['ENDIR'])})
    if db2result['FYRND']:
        station_attributes.append({'date_terminated': str(db2result['FYRND'])})
    station['attributes'] = station_attributes


    if db2result['ATHS']:
        station['comment'] = db2result['ATHS']

    #Get items from access_taeki (pg)
    acc_result = cur_acc.execute("""
                    select t.upphaf as taeki_upphaf, t.endir as taeki_endir, ts.upphaf as session_start, ts.endir as session_end, t.radnr, tg.lysing as gerd, t.lysing as taeki_comment, ts.aths||coalesce(chr(10)||'Upphaf:'||ts.uph_aths,'')||coalesce(chr(10)||'Endir:'||ts.end_aths,'') as session_comment
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
        if record['session_start']:
            item['date_from'] = record['session_start']
        if record['session_end']:
            item['date_to'] = record['session_end']
        
        if record['taeki_comment']:
            attribute = {'comment' : record['taeki_comment']}
            if record['session_start']:
                attribute['date_from'] = record['session_start']
            if record['session_end']:
                attribute['date_to'] = record['session_end']
            item['attributes'].append(attribute)

        if record['session_comment']:
            attribute = {'comment' : record['session_comment']}
            if record['session_start']:
                attribute['date_from'] = record['session_start']
            if record['session_end']:
                attribute['date_to'] = record['session_end']
            item['attributes'].append(attribute)

        if record['taeki_upphaf']:
            item['attributes'].append({'date_start' : record['taeki_upphaf']})
        if record['taeki_endir']:
            item['attributes'].append({'date_end' : record['taeki_endir']})

        items.append(item)
    station['items'] = items

    #{"marker":"TEST",
    #"name": "TEST",
    #"lat":"64.8167",
    #"lon":"18.8167",
    #"altitude":"1000",
    #"station_type_code":"sj",
    #"agency":"Veðurstofa Íslands",
    #    "items":[{"item_type":"antenna","serial_number":"test","date_from":"2015-06-30 00:00:00","attributes":[{"description":"testdesc1","date_from":"2015-01-01 00:00:00","date_to":"2016-05-05 00:00:00"}]},
    #            {"item_type":"radome","serial_number":"test2","attributes":[{"description":"testdesc2","date_from":"2015-05-05 00:00:00","date_to":"2016-05-05 00:00:00"}]}]
    #}

    #print json.dumps(station, cls=JSONDateEncoder)
    r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station, cls=JSONDateEncoder))
    print r.text




    #Fetch next result
    db2result = ibm_db.fetch_assoc(stmt)



#Stations present in Access, but not in STA.STOD
#Get items from access_taeki (pg)
cur_acc.execute("""
              select s.*,st.skst as station_type_code, se.lysing as agency
                from stod s
                left join stod_tegund st
                  on s.teg=st.tegund
                left join stod_eigandi se
                  on s.eigandi=se.eigandi
                where stod in (5847,8308,8311,8500,8610,71233,71234,71235,71236,71237,71238,71239,71240,71241,71243,71244,71245,71246,8309)
            """)
acc_stations = cur_acc.fetchall()

for record in acc_stations:
    marker = record['skst']
    station = { 'marker': marker, 
                'name': record['nafn'], 
                'station_type_code': record['station_type_code'], 
                'agency': record['agency']
                }
    if record['breidd_y']:
        station['lat'] = str(record['breidd_y'])
    if record['lengd_x']:
        station['lon'] = str(record['lengd_x'])
    if record['h_stod']:
        station['altitude'] = str(record['h_stod'])

    #Get items from access_taeki (pg)
    acc_result = cur_acc.execute("""
                    select t.upphaf as taeki_upphaf, t.endir as taeki_endir, ts.upphaf as session_start, ts.endir as session_end, t.radnr, tg.lysing as gerd, t.lysing as taeki_comment, ts.aths||coalesce(chr(10)||'Upphaf:'||ts.uph_aths,'')||coalesce(chr(10)||'Endir:'||ts.end_aths,'') as session_comment
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
        if record['session_start']:
            item['date_from'] = record['session_start']
        if record['session_end']:
            item['date_to'] = record['session_end']
        
        if record['taeki_comment']:
            attribute = {'comment' : record['taeki_comment']}
            if record['session_start']:
                attribute['date_from'] = record['session_start']
            if record['session_end']:
                attribute['date_to'] = record['session_end']
            item['attributes'].append(attribute)

        if record['session_comment']:
            attribute = {'comment' : record['session_comment']}
            if record['session_start']:
                attribute['date_from'] = record['session_start']
            if record['session_end']:
                attribute['date_to'] = record['session_end']
            item['attributes'].append(attribute)

        if record['taeki_upphaf']:
            item['attributes'].append({'date_start' : record['taeki_upphaf']})
        if record['taeki_endir']:
            item['attributes'].append({'date_end' : record['taeki_endir']})

        items.append(item)
    station['items'] = items


    #print json.dumps(station, cls=JSONDateEncoder)
    r = requests.post('https://tos-zato.dev.vedur.is/tos/station', data = json.dumps(station, cls=JSONDateEncoder))
    print r.text



#Close
#conn_db2.close()
conn_acc.close()

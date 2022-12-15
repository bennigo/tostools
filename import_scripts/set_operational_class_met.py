#!/usr/bin/python
# coding=utf-8
#
# Project: ToS
# Authors: Tryggvi Hjörvar
# Date: Aug 2019
# 
# Script to set new attribute operational_class to stations
#

import sys
import datetime
from datetime import datetime
import json
import requests
from datetime import datetime
import csv



#----JSONDateEncoder----
class JSONDateEncoder(json.JSONEncoder):
    """ Custom JSON encoder to handle datetime objects
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat(" ")
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)



#Load operational_class station list
with open('operational_class_met.csv', 'r') as csvfile:
    csv = csv.reader(csvfile, delimiter='\t')
    next(csv, None)  #Skip header
    for row in csv:
        #print row
        #print ', '.join(row)
        marker=row[0]
        flokkun=row[1]

        #Lookup station in TOS
        query={"code": "marker","value": marker}
        r = requests.post('https://tos-zato.dev.vedur.is/tos/v1/entity/search/station/meteorological/', data = json.dumps(query))
        if r.status_code==200:
            station = r.json()
            id_entity=station[0]['id_entity']
            found=False
            for attribute in station[0]['attributes']:
                #if attribute['code']=='marker':
                #    print attribute['value']
                if attribute['code']=='operational_class':
                    operational_class=attribute['value']
                    found=True
                    break
            if not found:
                print marker, 'no operational_class'
                #{"code":"operational_class","value":"B","date_from":"2019-08-21 00:00","date_to":null,"id_entity":790}
                attribute={
                    'code': 'operational_class',
                    'value': flokkun,
                    'date_from': '2019-08-21 00:00',
                    'date_to': None,
                    'id_entity': id_entity
                    }
                #print json.dumps(attribute, cls=JSONDateEncoder)
                r = requests.post('https://tos-zato.dev.vedur.is/tos/v1/attribute_values/', data = json.dumps(attribute, cls=JSONDateEncoder), headers=headers)
                #if r.text[0:9] == 'Traceback':
                #    print r.text
            else:
                print marker, 'operational_class: ' + operational_class

        else:
            print 'ERROR:' +marker+' NOT FOUND'
            sys.exit(1)


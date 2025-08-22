#!/usr/bin/python3

import logging
import requests


url_rest_tos='https://vi-api.vedur.is:11223/tos/v1'

#station = {'id_entity_parent': 1349}
station = {'id_entity_parent': 4392}

#Get contacts
station['contacts'] = []
response = requests.get(url_rest_tos + '/entity_contacts/'+str(station['id_entity_parent'])+'/', headers=None)
if response:
    try:
        for entity_contact in response.json():
            #print('entity_contact',entity_contact)
            if entity_contact['contact_end_date'] is None and entity_contact['role'] == 'owner':
                station['owner'] = entity_contact['name']
    except:
        logging.warning("Could not determine station contact for %s",station['station_identifier'])

print(station)

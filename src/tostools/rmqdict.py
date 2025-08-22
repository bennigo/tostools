
        station = {}
        station['station_identifier'] = station_identifier
        station['sensor_location'] = 'metadata'
        station['sensor_identifier'] = 'gps'
        station['observation_time'] = datetime.now()
        station['monitoring'] = {'passed': [], 'caught': []}
        
{'monitoring.quality.gps.metadata.consistency.rinex_tos_conflict'{
                'severity': 'critical',
                'max_observation_time': arrival[1]
            }

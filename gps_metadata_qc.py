#!/usr/bin/python3.1
#
# Project: gps_metadata
# Authors: Benedikt Gunnar Ófeigsson
#          parts edited TOSTools authored by Tryggvi Hjörvar
# Date: april 2022
#
#

import logging
from os import statvfs

url_rest_tos = "https://vi-api.vedur.is/tos/v1"


def get_logger(name=__name__, level=logging.WARNING):
    """
    logger to use within the modules
    """

    # Create log handler
    logHandler = logging.StreamHandler()
    # logHandler.setLevel(level)

    # Set handler format
    logFormat = logging.Formatter("[%(levelname)s] %(funcName)s: %(message)s")
    logHandler.setFormatter(logFormat)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()
    # Add handler to logger
    logger.addHandler(logHandler)

    # Stop propagating the log messages to root logger
    logger.propagate = False

    return logger


def rinex_labels():
    """ """

    searchlist = [
        "MARKER NAME",
        "MARKER NUMBER",
        "OBSERVER / AGENCY",
        "REC # / TYPE / VERS",
        "ANT # / TYPE",
        "APPROX POSITION XYZ",
        "ANTENNA: DELTA H/E/N",
        "INTERVAL",
        "TIME OF FIRST OBS",
    ]
    # splitlist = [
    #     (60,),
    #     (
    #         20,
    #         60,
    #     ),
    #     (
    #         20,
    #         20 + 40,
    #     ),
    #     (
    #         20,
    #         20 + 20,
    #         20 + 20 + 20,
    #     ),
    #     (
    #         20,
    #         20 + 20,
    #         60,
    #     ),
    #     (
    #         14,
    #         2 * 14,
    #         3 * 14,
    #         60,
    #     ),
    #     (
    #         14,
    #         2 * 14,
    #         3 * 14,
    #         60,
    #     ),
    #     (
    #         11,
    #         60,
    #     ),
    #     (
    #         6,
    #         2 * 6,
    #         3 * 6,
    #         4 * 6,
    #         5 * 6,
    #         43,
    #         48,
    #         51,
    #         60,
    #     ),
    # ]
    fortran_format_list = [
        "A60,A20",
        "A20,A40,A20",
        "A20,A40,A20",
        "A20,A20,A20,A20",
        "A20,A20,A20,A20",
        "3F14.4,A18,A20",
        "3F14.4,A18,A20",
        "F10.3,A50,A20",
        "5I6,F13.7,5X,A3,A9,A20",
    ]

    return searchlist, fortran_format_list


def searchStation(
    station_identifier,
    code="marker",
    url_rest=url_rest_tos,
    domains=None,
    loglevel=logging.WARNING,
):
    """
    comment
    """

    import json
    import sys

    import requests

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    if domains is None:
        domains = [
            "meteorological",
            "geophysical",
            "hydrological",
            "remote_sensing",
            "remote_sensing_platform",
            "general",
        ]
        module_logger.info("No domains specified, searcing " + str(domains))
    else:
        domains = list(domains.split(","))

    if "remote_sensing" in domains and "remote_sensing_platform" not in domains:
        domains.append("remote_sensing_platform")

    station_identifiers = [station_identifier]
    # Always include search for lowercase except for VM
    if not station_identifier.islower() and not (
        station_identifier[0].lower() == "v" and station_identifier[1].isdigit()
    ):
        station_identifiers += [station_identifier.lower()]
        module_logger.info(
            f"Including lowercase search for {station_identifier.lower()}"
        )

    # Remove padding 0 in search for VM
    if station_identifier[0:2] == "V0":
        station_identifiers += ["V" + station_identifier[2:]]
        module_logger.info(
            "Including unpadded search for " + "V" + station_identifier[2:]
        )

    stations = []
    for station_identifier in station_identifiers:
        for domain in domains:
            # Construct POST query
            # body = {"code": code, "value": 'GPS st\\u00f6\\u00f0'}
            # body = {"code": code, "value": u'GPS stöð'}
            body = {"code": code, "value": station_identifier}

            if domain == "remote_sensing_platform":
                entity_type = "platform"
            else:
                entity_type = "station"

            # Query TOS api
            try:
                response = requests.post(
                    url_rest + "/entity/search/" + entity_type + "/" + domain + "/",
                    data=json.dumps(body), headers = {'Content-Type': 'application/json'}
                )
            except requests.ConnectionError as error:
                module_logger.error(
                    "Failed to establish connection to {} with error {}".format(
                        url_rest, error
                    )
                )
                sys.exit(1)

            response.raise_for_status()
            if response.content:
                # data={}
                for station in response.json():
                    # Get current location for remote_sensing_platform location
                    if (
                        station["id_entity_parent"]
                        and station["code_entity_subtype"] == "remote_sensing_platform"
                    ):
                        location = getEntity(station["id_entity_parent"])
                        if location:
                            station["location"] = []
                            # station['location']=location
                            station["location"].append(
                                next(
                                    (
                                        item
                                        for item in location["attributes"]
                                        if (
                                            item["code"] == "name"
                                            and item["date_to"] is None
                                        )
                                    ),
                                    {"value": None},
                                )
                            )
                            station["location"].append(
                                next(
                                    (
                                        item
                                        for item in location["attributes"]
                                        if (
                                            item["code"] == "lat"
                                            and item["date_to"] is None
                                        )
                                    ),
                                    {"value": None},
                                )
                            )
                            station["location"].append(
                                next(
                                    (
                                        item
                                        for item in location["attributes"]
                                        if (
                                            item["code"] == "lon"
                                            and item["date_to"] is None
                                        )
                                    ),
                                    {"value": None},
                                )
                            )
                            # station['lat'] = next((item for item in location['attributes'] if (item['code'] == 'lat' and item['date_to'] is None)), {'value': None})
                            # station['lon'] = next((item for item in location['attributes'] if (item['code'] == 'lon' and item['date_to'] is None)), {'value': None})
                            # value = next((item for item in location['attributes'] if (item['code'] == 'lat' and item['date_to'] is None)), {'value': None})['value']
                            # if value:
                            #    station['lat'] = float(value)
                            # value = next((item for item in location['attributes'] if (item['code'] == 'lon' and item['date_to'] is None)), {'value': None})['value']
                            # if value:
                            #    station['lon'] = float(value)

                    stations.append(station)
                    # stations.append(data)

    return stations


def device_attribute_history(device, session_start, session_end):
    """
    sort out history within device
    """
    connections = []

    dates_from = set(
        [attribute["date_from"] for attribute in device["attributes"]]
    )

    key_list = [
        'serial_number',
        'model',
        'firmware_version',
        'software_version',
        'antenna_height',
        'antenna_offset_north',
        'antenna_offset_east',
        'antenna_reference_point',
        'date_from',
        'date_to',
    ]
    collection = dict.fromkeys(key_list[:-2])
    for date_from in sorted(dates_from):
        connection = dict.fromkeys(key_list)
        connection["code_entity_subtype"] = device["code_entity_subtype"]
        # tmp_list = key_list
        for item in device["attributes"]:
            # if device["code_entity_subtype"] == 'antenna':
            #     print(item['date_from'])
            #     print(date_from)

            if item["code"] in key_list:
                if date_from == item['date_from']:
                    if item["value"]:
                        connection[item["code"]] = item["value"]
                        collection[item["code"]] = item["value"]

                        if date_from >= session_start:
                            connection['date_from'] = date_from
                        else:
                            connection['date_from'] = session_start

                        if session_end is None:
                            if item['date_to'] is not None:
                                connection['date_to'] = item['date_to']
                        else:
                            if item['date_to'] is not None:
                                if item['date_to'] <= session_end:
                                    connection['date_to'] = item['date_to']
                else:
                    if item['code'] not in ["date_from", "date_to"]:
                        connection[item["code"]] = collection[item["code"]]

        connections.append(connection)

    return connections


def getContacts(id_entity_parent, url_rest, loglevel=logging.WARNING):
    """
    get station contacts
    """
    import requests

    contact = {}
    module_logger = get_logger(name=__name__, level=loglevel)

    try:
        owner_response = requests.get(
            url_rest
            + "/entity_contacts/"
            + str(id_entity_parent)
            + "/"
        )
        owners = owner_response.json()
        module_logger.debug("Owners {}".format(owners))
        for owner in owners:
            contact[owner["role"]] = {
                "role_is": owner["role_is"],
                "name": owner["name"],
            }
            module_logger.debug(
                "{}: {}".format(owner["role_is"], owner["name"])
            )
    except:
        module_logger.info(
            "Failed to establish connection to {}".format(url_rest)
        )
        contact["owner"] = {
            "role_is": "Eigandi stöðvar",
            "name": "Veðurstofa Íslands",
        }
        contact["operator"] = {
            "role_is": "Rekstraraðili stöðvar",
            "name": "Veðurstofa Íslands",
        }
        module_logger.debug(
            "Setting role of contact: {}".format(contact["operator"]["name"])
        )

    if contact["owner"]["name"] == "Landmælingar Íslands":
        contact["operator"] = {
            "role_is": "Rekstraraðili stöðvar",
            "name": "Landmælingar Íslands",
        }
        module_logger.debug(
            "Setting role of contact: {}: {}".format(
                contact["operator"]["role_is"], contact["operator"]["name"]
            )
        )

    if "contact" not in contact.keys():
        contact["contact"] = {
            "role_is": "tengiliður stöðvar",
            "name": "Veðurstofa Íslands",
        }
        module_logger.debug(
            "Setting role of contact: {}: {}".format(
                contact["contact"]["role_is"], contact["contact"]["name"]
            )
        )
    if "operator" not in contact.keys():
        contact["operator"] = {
            "role_is": "Rekstraraðili stöðvar",
            "name": "Veðurstofa Íslands",
        }
        module_logger.debug(
            "Setting role of contact: {}: {}".format(
                contact["operator"]["role_is"], contact["operator"]["name"]
            )
        )
    module_logger.info("contact: {}".format(contact))

    return contact


def gps_metadata(station_identifier, url_rest, loglevel=logging.WARNING):
    """
    input:
        Accessing TOS for GPS metadata
        station: station 4 letter marker
        url_res: rest service endpoint to access TOS
    """

    import sys
    from datetime import datetime

    import requests

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)
    domain = "geophysical"
    # code = "marker"
    # Tos wants lower case marker
    # stat = stat.lower()
    try:
        station = searchStation(
            station_identifier,
            url_rest=url_rest,
            domains=domain,
            loglevel=logging.WARNING,
        )[0]
        module_logger.setLevel(loglevel)
    except IndexError as error:
        module_logger.error(
            "{} station {} not found in TOS database. \
            Error {}".format(
                domain, station_identifier, error
            )
        )
        return []
    module_logger.debug("TOS station dictionary: {}".format(station))

    id_entity = station["id_entity"]
    module_logger.debug("station id: {}".format(id_entity))
    station = {}  # clear dictionary for later use
    module_logger.info(
        'Sending request "{}"'.format(
            url_rest + "/history/entity/" + str(id_entity) + "/"
        )
    )
    response = requests.get(url_rest + "/history/entity/" + str(id_entity) + "/")
    devices_history = response.json()
    module_logger.debug("TOS station dictionary: {}".format(devices_history))
    module_logger.debug(
        "TOS station dictionary keys: {}".format(devices_history.keys())
    )
    module_logger.info(
        "Station attributes: {}".format(
            [attribute["code"] for attribute in devices_history["attributes"]]
        )
    )
    for attribute in devices_history["attributes"]:
        if attribute["code"] in [
            "marker",
            "name",
            "iers_domes_number",
            "in_network_epos",
        ]:
            station[attribute["code"]] = attribute["value"]
        elif attribute["code"] in ["lon", "lat", "altitude"]:
            station[attribute["code"]] = float(attribute["value"])

    contact = {}
    sessions = []
    device_sessions = []
    for connection in devices_history["children_connections"]:
        # NOTE: ignoring sessions that have 0 duration
        if connection['time_from'] == connection['time_to']:
            module_logger.info(
                "Session start is the same as session end: {}, end: {}"
                .format(connection['time_from'], connection['time_to'])
            )
            continue
        id_entity_child = connection["id_entity_child"]
        module_logger.debug("{0}:\t{1}".format("id_entity_child", id_entity_child))
        try:
            module_logger.info(
                'sending request "{}"'.format(
                    url_rest + "/history/entity/" + str(id_entity_child) + "/"
                )
            )
            devices_response = requests.get(
                url_rest + "/history/entity/" + str(id_entity_child) + "/"
            )
            device = devices_response.json()
            module_logger.debug("device {}".format(device))
        except:
            module_logger.error("failed to establish connection to {}".format(
                                    url_rest
                                ))
            sys.exit(1)
        module_logger.debug(
            "{0}:\t{1}".format(
                "id_entity_parent",
                connection["id_entity_parent"]
            )
        )

        if not contact:
            station["contact"] = getContacts(
                                    connection["id_entity_parent"],
                                    url_rest
                                )

        devices_used = ["gnss_receiver", "antenna", "radome", "monument"]
        if device["code_entity_subtype"] in devices_used:
            print("------ device['code_entity_subtype']: {} ---------"
                  .format(device['code_entity_subtype'])
                  )
            attribute_history = device_attribute_history(
                device,
                connection['time_from'],
                connection['time_to']
            )
            for attribute in attribute_history:
                # BUG: need to solve device attribute history
                #      proper date_from and to for all session changes
                #      curently only done for anntenna height
                # if attribute['antenna_height']:
                #     # print(attribute)
                #     # print("%"*60)
                #     if attribute['date_to'] is not None:
                #         connection['time_to'] = attribute['date_to']
                #
                #     # print(attribute)
                #     print(
                #         "date_from: {}, date_to: {}".
                #         format(attribute['date_from'], attribute['date_to'])
                #     )
                #     if connection['time_from'] != attribute['date_from']:
                #         connection['time_from'] = attribute['date_from']
                #         connection['time_to'] = attribute['date_to']

                # print(attribute)
                connection["device"] = attribute
                device_sessions.append(connection.copy())

            print(
                "time_from: {}, time_to: {}".
                format(connection['time_from'], connection['time_to'])
            )
    # Sort by time_from
    device_sessions.sort(key=lambda d: d["time_from"])

    for device_session in device_sessions:
        code_entity_subtype = device_session["device"]["code_entity_subtype"]

        try:
            time_from = datetime.strptime(
                device_session["time_from"], "%Y-%m-%dT%H:%M:%S"
            )
        except:
            time_from = None

        try:
            time_to = datetime.strptime(device_session["time_to"], "%Y-%m-%dT%H:%M:%S")
        except:
            time_to = None

        model = device_session["device"]["model"]
        serial_number = device_session["device"]["serial_number"]

        if code_entity_subtype == "gnss_receiver":
            module_logger.debug("device_session: {}".format(device_session["device"]))
            firmware_version = device_session["device"]["firmware_version"]
            software_version = device_session["device"]["software_version"]

            sessions.append(
                {
                    "time_from": time_from,
                    "time_to": time_to,
                    "gnss_receiver": {
                        "model": model,
                        "serial_number": serial_number,
                        "firmware_version": firmware_version,
                        "software_version": software_version,
                    },
                }
            )

        if code_entity_subtype == "antenna":
            module_logger.debug("device_session: {}".format(device_session["device"]))
            antenna_height = device_session["device"]["antenna_height"]
            if antenna_height is None:
                antenna_height = 0.0
            else:
                antenna_height = float(antenna_height)

            antenna_reference_point = device_session["device"][
                "antenna_reference_point"
            ]

            sessions.append(
                {
                    "time_from": time_from,
                    "time_to": time_to,
                    "antenna": {
                        "model": model,
                        "serial_number": serial_number,
                        "antenna_height": antenna_height,
                        "antenna_reference_point": antenna_reference_point,
                    },
                }
            )

        if code_entity_subtype == "radome":
            module_logger.debug("device_session: {}".format(device_session["device"]))

            sessions.append(
                {
                    "time_from": time_from,
                    "time_to": time_to,
                    "radome": {"model": model, "serial_number": serial_number},
                }
            )

        if code_entity_subtype == "monument":
            module_logger.debug("device_session: {}".format(device_session["device"]))

            monument_height = device_session["device"]["antenna_height"]
            if monument_height is None:
                monument_height = 0.0
            else:
                monument_height = float(monument_height)

            monument_offset_north = device_session["device"]["antenna_offset_north"]
            if monument_offset_north is None:
                monument_offset_north = 0.0
            else:
                monument_offset_north = float(monument_offset_north)

            monument_offset_east = device_session["device"]["antenna_offset_east"]
            if monument_offset_east is None:
                monument_offset_east = 0.0
            else:
                monument_offset_east = float(monument_offset_east)

            sessions.append(
                {
                    "time_from": time_from,
                    "time_to": time_to,
                    "monument": {
                        "model": model,
                        "serial_number": serial_number,
                        "monument_height": monument_height,
                        "monument_offset_north": monument_offset_north,
                        "monument_offset_east": monument_offset_east,
                    },
                }
            )

    sessions_start = iter(sorted({session["time_from"] for session in sessions}))
    sessions_end = iter(
        sorted(
            {
                session["time_to"]
                for session in sessions
                if (session["time_to"] is not None)
            }
        )
    )

    station_history = []
    for start in sessions_start:
        try:
            end = next(sessions_end)
        except StopIteration:
            end = None
        module_logger.warning("session start-end: {}-{}".format(start, end))

        station_session = {}
        station_session["time_from"] = start
        station_session["time_to"] = end
        for session in sessions:
            if end:
                if session["time_from"] <= start:
                    if session["time_to"] is not None and session["time_to"] >= end:
                        module_logger.debug("Session: {}".format(session))
                        device = [key for key in session.keys() if key in devices_used][
                            0
                        ]
                        station_session[device] = session[device]

                    elif session["time_to"] is None:
                        module_logger.debug("Session: {}".format(session))
                        device = [key for key in session.keys() if key in devices_used][
                            0
                        ]
                        station_session[device] = session[device]
            else:
                if session["time_to"] is None:
                    module_logger.debug("Session: {}".format(session))
                    device = [key for key in session.keys() if key in devices_used][0]
                    station_session[device] = session[device]
        station_history.append(station_session)

    station["device_history"] = station_history
    module_logger.debug(station)

    return station


def fileList(
    station,
    start=None,
    end=None,
    pdir="/mnt_data/rawgpsdata",
    freqd="15s_24hr",
    rawdir="rinex",
    fform="#Rin2",
    DZend="D.Z",
    loglevel=logging.WARNING,
):
    """
    Returns a list of potential station RINEX files from a given station dictionary as returned by gps_metadata()
    grouped according to station sessions.
    input:
        station:
    """

    from datetime import timedelta
    from pathlib import PurePath

    from gtimes import timefunc as tf
    from gtimes.timefunc import datefRinex

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    filesList = []
    stat = station["marker"].upper()
    formatString = (
        pdir
        + "/%Y/#b/"
        + stat
        + "/"
        + freqd
        + "/"
        + rawdir
        + "/"
        + stat
        + fform
        + DZend
    )

    module_logger.info("Initial period: {}\t{}\n".format(start, end) + "*" * 50)

    for item in station["device_history"]:
        module_logger.info(
            "Session period: {}\t{}".format(item["time_from"], item["time_to"])
        )

        flist = []
        session_flag = True
        if item["time_to"] is None:
            time_to = tf.currDatetime(days=-1)
        else:
            time_to = item["time_to"]

        if item["time_from"] is not None:
            time_from = item["time_from"]

        if start is not None:
            if time_to < start:
                session_flag = False

            if time_from <= start:
                time_from = start

        if end is not None:
            if end < time_from:
                session_flag = False

            if end < time_to:
                time_to = end

        module_logger.info("Current period: {}\t{}".format(time_from, time_to))
        session_nr = station["device_history"].index(item)
        module_logger.info("Index number: {}".format(session_nr))

        if session_flag:
            flist = tf.datepathlist(formatString, "1D", time_from, time_to, closed=None)
            # Add one day to compensate for edge effect of open 'right' boundaries used in datepathlist
            # But not if last day is to day i.e end is
            endfile = PurePath(flist[-1]).name
            endfile_date = datefRinex([endfile])[0]
            if (
                time_to - endfile_date == timedelta(1)
                and time_to != item["time_to"]
                and end is not None
            ):
                module_logger.debug("{}".format(time_to - endfile_date))
                flist.append(
                    tf.datepathlist(formatString, "1D", end, end, closed="left")[0]
                )

            filesList.append(
                {
                    "marker": stat,
                    "session_number": session_nr,
                    "time_from": item["time_from"],
                    "time_to": item["time_to"],
                    "filelist": flist,
                }
            )

    if module_logger.getEffectiveLevel() <= 10 and filesList:
        for flist in filesList:
            module_logger.debug(
                "Station: {}, Session number: {}".format(
                    flist["marker"], flist["session_number"]
                )
            )
            module_logger.debug("{}\t{}".format(flist["time_from"], flist["time_to"]))

            if flist["filelist"]:
                module_logger.debug(flist["filelist"][0])
                module_logger.debug(flist["filelist"][-1])
            else:
                module_logger.debug(flist["filelist"])
    else:
        module_logger.debug(
            "filesList empty, logging level: {}\tfilesList: {}".format(
                module_logger.getEffectiveLevel(), filesList
            )
        )

    return filesList


def extract_from_rheader(rheader, loglevel=logging.WARNING):
    """
    Extracts lines containing the keywords in "searchlist" from a Rinex header string and returns as dictonary with keyword as keys
    and content of the lines in as items.
    input:
        rheader: header section of a Rinex file as a single string
    output:
        returns dictionary containing the keywords in searchlist as key's and variables in the relevant lines as items
        and rinex file name and path in key "rinex file"

    """
    import re
    from datetime import datetime as dt

    import fortranformat as ff
    from gtimes.timefunc import datefRinex

    module_logger = get_logger(name=__name__, level=loglevel)

    module_logger.debug(
        "Rinex file: {1} in directory {0}".format(*rheader["rinex file"])
    )
    module_logger.debug("Rinex header:\n{}".format(rheader["header"]))

    fname_date = datefRinex([rheader["rinex file"][1]])[0]
    module_logger.debug("{}: {}".format(rheader["rinex file"][1][0:4], fname_date))

    searchlist, fortran_format_list = rinex_labels()
    module_logger.debug("Strings to search for: {}".format(searchlist))

    rinex_header_dict = rinext_test_dict = {"rinex file": rheader["rinex file"]}
    # for string, fformat in zip(searchlist, fortran_format):

    for string, fortran_format in zip(searchlist, fortran_format_list):
        pattern = r"(^.*(?:{}).*$)".format(string)
        module_logger.debug("Pattern to match: {}".format(pattern))

        module_logger.debug("Length of pattern string: {}".format(len(string)))

        mstring = re.compile(pattern, re.M)
        result = mstring.search(rheader["header"])

        if result:

            matched_line = result.group()
            module_logger.info("Matched line: {}".format(matched_line))

            matched_list = []

            format_reader = ff.FortranRecordReader(fortran_format)
            module_logger.debug("format string: {}".format(format_reader.format))
            matched_list = format_reader.read(matched_line)

            matched_list[:] = [
                string.strip() if type(string) is str else string
                for string in matched_list
            ]

            if matched_list[-1] == "TIME OF FIRST OBS":
                # matched_list[:-3] = list(map(int, matched_list[:-3]))
                time_first_obs = dt(*matched_list[:-4], round(float(matched_list[-4])))
                matched_list[:-1] = [time_first_obs, matched_list[-3], matched_list[-2]]
                module_logger.debug(
                    "{}: {}".format(matched_list[-1], matched_list[:-1])
                )

            # module_logger.warning("Rinex line: {}".format(match_list_test))
            module_logger.info("Rinex line: {}".format(matched_list))

            rinex_header_dict[matched_list[-1]] = matched_list[:-1]

    module_logger.debug("rinex_header_dict: {}".format(rinex_header_dict))

    return rinex_header_dict


def compare_TOS_to_rinex(rinex_dict, session, loglevel=logging.WARNING):
    """
    Reads in dictionary containing variables from the following
    line of a rinex header:
    'MARKER NAME', 'MARKER NUMBER', "OBSERVER / AGENCY", "REC # / TYPE / VERS",
    "ANT # / TYPE", "APPROX POSITION XYZ", "ANTENNA: DELTA H/E/N", "INTERVAL",
    "TIME OF FIRST OBS"
    and compares these varables to the relevant variables in TOS database

    input:
        rinex_dict: dictionary containing variables from a rinex header
        session: dictionary containing variables from TOS database
        loglevel: loglevel

    output:
        returns a dictionary containing those variables from TOS database that
        don't match the rinex header
    """

    from datetime import datetime as dt
    from datetime import timedelta
    from pathlib import Path, PurePath

    import geofunc.geo as geo
    import numpy as np
    from gtimes import timefunc as tf
    from gtimes.timefunc import datefRinex
    from pyproj import CRS, Transformer

    # defining coordinate systems
    itrf2008 = CRS("EPSG:5332")
    wgs84 = CRS("EPSG:4326")
    # setting up the transformations.
    itrf08towgs84 = Transformer.from_crs(itrf2008, wgs84)
    wgs84toitrf08 = Transformer.from_crs(wgs84, itrf2008)

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    module_logger.debug("session.keys: {}".format(session.keys()))
    module_logger.debug("session dictionary: {}".format(session))

    remove_labels = ["TIME OF FIRST OBS"]
    searchlist, _ = rinex_labels()
    [searchlist.remove(label) for label in remove_labels if label in searchlist]
    rinex_header_labels = iter(
        [item for item in rinex_dict.keys() if item not in remove_labels]
    )
    module_logger.debug("rinex_dict: {}".format(rinex_dict))

    searchlist.append("rinex file")
    rinex_correction_dict = {}  # to collect inconsistansies

    for label in rinex_header_labels:
        module_logger.info('Checking "{}"'.format(label))
        searchlist.remove(label)

        match label:
            case "rinex file":
                # This should always match
                # Any mismach here will return a string with the rinex  file name This reprecents reprecents some serious issues which might be due to code bug or serious issue with file structure
                rinex_file_fullpath = Path(*rinex_dict[label])

                module_logger.info("Rinex path: {}".format(rinex_file_fullpath))
                if rinex_file_fullpath.is_file():
                    module_logger.info(
                        "Rinex file: {} exists".format(rinex_file_fullpath)
                    )
                    rinex_correction_dict[label] = rinex_dict[label]
                else:
                    module_logger.error(
                        "Rinex file {} does not appear to exist. This should not happen".format(
                            rinex_file_fullpath
                        )
                    )
                    rinex_correction_dict[label] = [
                        rinex_file_fullpath.as_posix(),
                        None,
                    ]

                    return rinex_correction_dict

                rinex_file = rinex_dict[label][1]
                module_logger.info("Rinex file: {}".format(rinex_file))
                TOS_marker = session["marker"].upper()
                TOS_session_period = [
                    session["device_history"]["time_from"],
                    session["device_history"]["time_to"],
                ]
                module_logger.info(
                    "session period: {} - {}".format(*TOS_session_period)
                )

                marker = rinex_file[:4]
                date_from_rinex_fname = datefRinex([rinex_file])[0]

                # date_from_rinex_file =
                try:
                    time_of_first_obs = rinex_dict["TIME OF FIRST OBS"][0]
                except KeyError as e:
                    module_logger.error(
                        'key "{}" not in dictionary "rinex_dict"'.format(e)
                    )
                    rinex_correction_dict["TIME OF FIRST OBS"] = [None]

                    return rinex_correction_dict

                module_logger.debug('{0} "{1}"'.format(label, rinex_file))
                if (
                    marker == TOS_marker
                    and date_from_rinex_fname.date() == time_of_first_obs.date()
                ):
                    module_logger.debug(
                        '{0} "{1}" has matching name prefix with database marker "{2}" and the doy-year in {1} matches the date of first observation {3}'.format(
                            label, rinex_file, TOS_marker, time_of_first_obs
                        )
                    )

                    if TOS_session_period[1] is not None:
                        if (
                            TOS_session_period[0]
                            <= date_from_rinex_fname
                            <= TOS_session_period[1]
                        ):
                            module_logger.debug(
                                'Time of file "{0}" falls within period "{2} <= {1} < {3}'.format(
                                    rinex_file,
                                    date_from_rinex_fname,
                                    *TOS_session_period,
                                )
                            )
                        else:
                            module_logger.error(
                                'Time of file "{0}": {1}. DOES NOT fall within period "{2} - {3}". This should not happen'.format(
                                    rinex_file,
                                    date_from_rinex_fname,
                                    *TOS_session_period,
                                )
                            )

                            rinex_correction_dict["session period"] = TOS_session_period

                            return rinex_correction_dict

                    else:
                        TOS_session_period[1] = tf.currDatetime(days=-1)
                        if (
                            TOS_session_period[0]
                            <= date_from_rinex_fname
                            <= TOS_session_period[1]
                        ):
                            module_logger.debug(
                                'Time of file "{0}" falls within period "{2} <= {1} < {3}'.format(
                                    rinex_file,
                                    date_from_rinex_fname,
                                    *TOS_session_period,
                                )
                            )
                        else:
                            module_logger.error(
                                'Time of file "{0}": {1}. DOES NOT fall within period "{2} - {3}". This should not happen'.format(
                                    rinex_file,
                                    date_from_rinex_fname,
                                    *TOS_session_period,
                                )
                            )

                            rinex_correction_dict["session period"] = TOS_session_period

                            return rinex_correction_dict

                else:
                    if marker != TOS_marker:
                        module_logger.error(
                            'Mismach with {0} "{1}" and matching name prefix in database marker "{2}" '.format(
                                label, rinex_file, TOS_marker
                            )
                        )
                        rinex_correction_dict["TOS marker"] = [TOS_marker]

                    if date_from_rinex_fname.date() != time_of_first_obs.date():
                        module_logger.error(
                            "Mismach with the doy-year in {0} and the date of first observation {1}".format(
                                rinex_file, time_of_first_obs
                            )
                        )
                        rinex_correction_dict["TIME OF FIRST OBS"] = [time_of_first_obs]

                    module_logger.debug(
                        "Returning dictionary {}".format(rinex_correction_dict)
                    )
                    return rinex_correction_dict

            case "MARKER NAME":
                rinex_marker = rinex_dict[label][0]
                module_logger.info(
                    '"Marker name" in Rinex file: {}'.format(rinex_marker)
                )
                TOS_marker = session["marker"].upper()
                if rinex_marker == TOS_marker:
                    module_logger.debug(
                        'Label "{0}" is "{1}" in file "{2}", matches database marker "{3}"'.format(
                            label, rinex_marker, rinex_dict["rinex file"], TOS_marker
                        )
                    )
                else:
                    module_logger.warning(
                        'Label "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label, rinex_marker, rinex_dict["rinex file"], TOS_marker
                        )
                    )
                    rinex_correction_dict[label] = [TOS_marker]

            case "MARKER NUMBER":
                rinex_number = rinex_dict[label][0]
                module_logger.info(
                    '"Marker number" in Rinex file: {}'.format(rinex_number)
                )
                if "iers_domes_number" in session.keys():
                    TOS_number = session["iers_domes_number"]
                else:
                    TOS_number = session["marker"].upper()

                if rinex_number == TOS_number:
                    module_logger.debug(
                        'Label "{0}" is "{1}" in file "{2}", matches database marker "{3}"'.format(
                            label, rinex_number, rinex_dict["rinex file"], TOS_number
                        )
                    )
                else:
                    module_logger.warning(
                        'Label "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label, rinex_number, rinex_dict["rinex file"], TOS_number
                        )
                    )
                    rinex_correction_dict[label] = [TOS_number, ""]

            case "OBSERVER / AGENCY":
                rinex_observer_agency = rinex_dict[label]
                module_logger.info(
                    '"OBSERVER / AGENCY" in Rinex file:\t{}\t{}'.format(
                        *rinex_observer_agency
                    )
                )
                contact_correction_list = [None, None]

                TOS_operator = session["contact"]["operator"]["name"]
                module_logger.info('"operator "agency":\t{}'.format(TOS_operator))

                if TOS_operator == "Veðurstofa Íslands":
                    TOS_observer_agency = ["BGO/HMF", "Vedurstofa Islands"]
                if TOS_operator == "Landmælingar Íslands":
                    TOS_observer_agency = ["LMI", "Landmaelingar Islands"]

                if rinex_observer_agency[0] != TOS_observer_agency[0]:
                    module_logger.warning(
                        'Label OBSERVER in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_observer_agency[0],
                            rinex_dict["rinex file"],
                            TOS_observer_agency[0],
                        )
                    )
                    contact_correction_list[0] = TOS_observer_agency[0]
                    rinex_correction_dict[label] = contact_correction_list

                if rinex_observer_agency[1] != TOS_observer_agency[1]:
                    module_logger.warning(
                        'Label OBSERVER in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_observer_agency[1],
                            rinex_dict["rinex file"],
                            TOS_observer_agency[1],
                        )
                    )
                    contact_correction_list[1] = TOS_observer_agency[1]
                    rinex_correction_dict[label] = contact_correction_list

            case "REC # / TYPE / VERS":
                rinex_receiver = rinex_dict[label]
                receiver_correction_list = [None, None, None]
                module_logger.info(
                    '"REC # / TYPE / VERS" in Rinex file: {} / {} / {} '.format(
                        *rinex_receiver
                    )
                )
                TOS_receiver_attributes = session["device_history"]["gnss_receiver"]
                module_logger.debug("{}".format(TOS_receiver_attributes))
                TOS_receiver_serial = TOS_receiver_attributes["serial_number"]
                TOS_receiver_model = TOS_receiver_attributes["model"]
                TOS_receiver_sversion = TOS_receiver_attributes["software_version"]

                if rinex_receiver[0] != TOS_receiver_serial:
                    module_logger.warning(
                        'Label REC # in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_receiver[0],
                            rinex_dict["rinex file"],
                            TOS_receiver_serial,
                        )
                    )
                    receiver_correction_list[0] = TOS_receiver_serial
                    rinex_correction_dict[label] = receiver_correction_list
                else:
                    module_logger.info(
                        'Label REC # in "{0}" is "{1}" in file "{2}", and matches database value "{3}"'.format(
                            label,
                            rinex_receiver[0],
                            rinex_dict["rinex file"],
                            TOS_receiver_serial,
                        )
                    )

                if rinex_receiver[1] != TOS_receiver_model:
                    module_logger.warning(
                        'Label TYPE  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_receiver[1],
                            rinex_dict["rinex file"],
                            TOS_receiver_model,
                        )
                    )
                    receiver_correction_list[1] = TOS_receiver_model
                    rinex_correction_dict[label] = receiver_correction_list
                else:
                    module_logger.info(
                        'Label TYPE in "{0}" is "{1}" in file "{2}", and matches database value "{3}"'.format(
                            label,
                            rinex_receiver[1],
                            rinex_dict["rinex file"],
                            TOS_receiver_model,
                        )
                    )

                if rinex_receiver[2] != TOS_receiver_sversion:
                    module_logger.warning(
                        'Label VERS  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_receiver[2],
                            rinex_dict["rinex file"],
                            TOS_receiver_sversion,
                        )
                    )
                    receiver_correction_list[2] = TOS_receiver_sversion
                    rinex_correction_dict[label] = receiver_correction_list
                else:
                    module_logger.info(
                        'Label VERS in "{0}" is "{1}" in file "{2}", and matches database value "{3}"'.format(
                            label,
                            rinex_receiver[2],
                            rinex_dict["rinex file"],
                            TOS_receiver_sversion,
                        )
                    )

            case "ANT # / TYPE":
                rinex_antenna = rinex_dict[label]
                antenna_correction_list = [
                    None,
                    None,
                    "",
                ]  # extra empty string for plank space in rinex file
                module_logger.info(
                    '"ANT # / TYPE" in Rinex file: {} / {} '.format(*rinex_antenna)
                )
                TOS_antenna_attributes = session["device_history"]["antenna"]
                module_logger.debug("{}".format(TOS_antenna_attributes))
                TOS_antenna_serial = TOS_antenna_attributes["serial_number"]
                TOS_antenna_model = TOS_antenna_attributes["model"]

                if "radome" in session["device_history"]:
                    TOS_radome_model = session["device_history"]["radome"]["model"]
                    module_logger.info("radome: {}".format(TOS_radome_model))
                    TOS_antenna_model = "{0:<16.16}{1:>4.4}".format(
                        TOS_antenna_model, TOS_radome_model
                    )
                    module_logger.info(
                        'Antenna type with radome "{}"'.format(TOS_antenna_model)
                    )

                if rinex_antenna[0] != TOS_antenna_serial:
                    module_logger.warning(
                        'Label ANT # in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_antenna[0],
                            rinex_dict["rinex file"],
                            TOS_antenna_serial,
                        )
                    )
                    antenna_correction_list[0] = TOS_antenna_serial
                    rinex_correction_dict[label] = antenna_correction_list
                else:
                    module_logger.debug(
                        'Label ANT # in "{0}" is "{1}" in file "{2}", and matches database value "{3}"'.format(
                            label,
                            rinex_antenna[0],
                            rinex_dict["rinex file"],
                            TOS_antenna_serial,
                        )
                    )

                if rinex_antenna[1] != TOS_antenna_model:
                    module_logger.warning(
                        'Label TYPE  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_antenna[1],
                            rinex_dict["rinex file"],
                            TOS_antenna_model,
                        )
                    )
                    antenna_correction_list[1] = TOS_antenna_model
                    rinex_correction_dict[label] = antenna_correction_list
                else:
                    module_logger.info(
                        'Label TYPE in "{0}" is "{1}" in file "{2}", and matches database value "{3}"'.format(
                            label,
                            rinex_antenna[1],
                            rinex_dict["rinex file"],
                            TOS_antenna_model,
                        )
                    )

            case "ANTENNA: DELTA H/E/N":
                rinex_antenna_offset_HEN = rinex_dict[label]
                antenna_offset_correction_list = [
                    None,
                    None,
                    None,
                    "",
                ]  # extra empty string for plank space in rinex file
                module_logger.info(
                    '"ANTENNA: DELTA H/E/N" in Rinex file:\t{}\t{}\t{}'.format(
                        *rinex_antenna_offset_HEN
                    )
                )

                TOS_antenna_attributes = session["device_history"]["antenna"]
                module_logger.debug("{}".format(TOS_antenna_attributes))
                TOS_antenna_height = TOS_antenna_attributes["antenna_height"]
                module_logger.debug("Antenna height: {}".format(TOS_antenna_height))

                TOS_monument_attributes = session["device_history"]["monument"]
                module_logger.info("{}".format(TOS_monument_attributes))
                TOS_monument_height = TOS_monument_attributes["monument_height"]
                module_logger.debug("Monument height: {}".format(TOS_monument_height))

                TOS_antenna_offset_HEN = [
                    TOS_antenna_height + TOS_monument_height,
                    0.0,
                    0.0,
                ]
                module_logger.debug(
                    "Antenna height + Monument height: {}".format(
                        TOS_antenna_offset_HEN[0]
                    )
                )

                if rinex_antenna_offset_HEN[0] != TOS_antenna_offset_HEN[0]:
                    module_logger.warning(
                        'Label H  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[0],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[0],
                        )
                    )
                    antenna_offset_correction_list[0] = TOS_antenna_offset_HEN[0]
                    rinex_correction_dict[label] = antenna_offset_correction_list
                else:
                    module_logger.debug(
                        'Label H  in "{0}" is "{1}" in file "{2}", matches database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[0],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[0],
                        )
                    )

                if rinex_antenna_offset_HEN[1] != TOS_antenna_offset_HEN[1]:
                    module_logger.warning(
                        'Label E  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[1],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[1],
                        )
                    )
                    antenna_offset_correction_list[1] = TOS_antenna_offset_HEN[1]
                    rinex_correction_dict[label] = antenna_offset_correction_list
                else:
                    module_logger.debug(
                        'Label E in "{0}" is "{1}" in file "{2}", matches database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[1],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[1],
                        )
                    )

                if rinex_antenna_offset_HEN[2] != TOS_antenna_offset_HEN[2]:
                    module_logger.warning(
                        'Label N  in "{0}" is "{1}" in file "{2}", DOES NOT match database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[2],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[2],
                        )
                    )
                    antenna_offset_correction_list[2] = TOS_antenna_offset_HEN[2]
                    rinex_correction_dict[label] = antenna_offset_correction_list
                else:
                    module_logger.debug(
                        'Label N in "{0}" is "{1}" in file "{2}", matches database value "{3}"'.format(
                            label,
                            rinex_antenna_offset_HEN[2],
                            rinex_dict["rinex file"],
                            TOS_antenna_offset_HEN[2],
                        )
                    )

            case "APPROX POSITION XYZ":
                rinex_xyz_coord = rinex_dict[label]
                module_logger.info("rinex_xyz_coord: {}".format(rinex_xyz_coord))
                module_logger.info(
                    '"XYZ Position" in Rinex file:\t{}\t{}\t{}'.format(*rinex_xyz_coord)
                )

                TOS_coord_latlonheig = [
                    session["lat"],
                    session["lon"],
                    session["altitude"],
                ]
                module_logger.info(
                    '"lat, lon, height coordinates" in TOS database:\t{}\t{}\t{}'.format(
                        *TOS_coord_latlonheig
                    )
                )
                TOS_coord_ECEF = list(wgs84toitrf08.transform(*TOS_coord_latlonheig))
                module_logger.info(
                    "XYZ coordinates in TOS database:\t{0:.4f}\t{1:.4f}\t{2:.4f}".format(
                        *TOS_coord_ECEF
                    )
                )

                Rinex_TOS_coord_difference = np.array(TOS_coord_ECEF) - np.array(
                    rinex_xyz_coord[:-1]
                )
                module_logger.info(
                    "difference between ECEF coordinates between Rinex file and TOS database in meters:\t{0:>.4f}\t{1:>.4f}\t{2:>.4f}".format(
                        *Rinex_TOS_coord_difference
                    )
                )
                distance = np.sqrt(
                    Rinex_TOS_coord_difference.dot(Rinex_TOS_coord_difference)
                )
                module_logger.info(
                    "Distance between coordinates:\t{0:>.4f} m".format(distance)
                )

                tolerance = 60.0
                if distance > tolerance:
                    module_logger.error(
                        "Distance between TOS database and Rinex files coordinates is more then {0:.4f} m < {1:.4f} m".format(
                            tolerance, distance
                        )
                    )
                    rinex_correction_dict[label] = [*TOS_coord_ECEF, ""]
                else:
                    module_logger.info(
                        "Distance between TOS database and Rinex files coordinates is less then {0:.4f} m > {1:.4f} m".format(
                            tolerance, distance
                        )
                    )

    else:
        module_logger.info(
            "OUT OF LABELS following labels where not handled {}".format(searchlist)
        )

        if "MARKER NUMBER" in searchlist:
            if "iers_domes_number" in session.keys():
                TOS_number = session["iers_domes_number"]
            else:
                TOS_number = session["marker"].upper()

            module_logger.info(
                '"MARKER NUMBER" is not in Rinex file adding {}'.format(TOS_number)
            )
            rinex_correction_dict["MARKER NUMBER"] = [TOS_number, ""]

    module_logger.debug("rinex_correction_dict: {}".format(rinex_correction_dict))

    return rinex_correction_dict


def fix_rinex_header(
    rinex_correction_dict, rinex_dict, rheader, loglevel=logging.WARNING
):
    """ """
    import re
    from pathlib import Path

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)
    module_logger.info(
        'keys in "rinex_correction_dict" {}'.format(rinex_correction_dict.keys())
    )
    module_logger.info(
        'keys in "rinex_correction_dict" {}'.format(rinex_correction_dict)
    )
    module_logger.info('keys in "rinex_dict" {}'.format(rinex_dict.keys()))
    module_logger.debug('keys in "rheader" {}'.format(rheader.keys()))

    if (
        rinex_correction_dict["rinex file"] != rinex_dict["rinex file"]
        or rheader["rinex file"] != rinex_dict["rinex file"]
    ):
        module_logger.debug("input dictionaries are not derived from the same files")
        module_logger.debug(
            'input rinex file is {} for "rinex_correction_dict"'.format(
                Path(*rinex_correction_dict["rinex file"])
            )
        )
        module_logger.debug(
            'input rinex file is {} for "rinex_dict"'.format(
                Path(*rinex_dict["rinex file"])
            )
        )
        module_logger.info(
            'input rinex file is {} for "rheader"'.format(Path(*rheader["rinex file"]))
        )
    else:
        module_logger.debug(
            "input dictionaries are derived from the same file {}".format(
                Path(*rinex_dict["rinex file"])
            )
        )

    rinex_header_line, fortran_format = rinex_labels()
    label_gen = (
        label for label in rinex_correction_dict.keys() if label not in ["rinex file"]
    )
    rinex_fix_list = []
    for label in label_gen:
        rinex_fix_line = fix_rinex_line(
            label, rinex_correction_dict, rinex_dict, loglevel=logging.WARNING
        )

        module_logger.info("Line to replace: {}".format(rinex_fix_line))
        pattern = r"(^.*(?:{}).*$)".format(label)
        module_logger.debug("Pattern to match: {}".format(pattern))
        module_logger.debug("Length of pattern string: {}".format(len(label)))

        mstring = re.compile(pattern, re.M)
        result = mstring.search(rheader["header"])
        if result:
            rheader["header"] = re.sub(mstring, rinex_fix_line, rheader["header"])
        else:
            label_list, _ = rinex_labels()
            prev_label = label_list[label_list.index(label) - 1]
            pattern = r"({}.*$)".format(prev_label)
            mstring = re.compile(pattern, re.M)
            rheader["header"] = re.sub(
                mstring, r"\1\n" + rinex_fix_line, rheader["header"]
            )

    return rheader


def fix_rinex_line(label, rinex_correction_dict, rinex_dict, loglevel=logging.WARNING):
    """ """

    import re

    import fortranformat as ff

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)
    rinex_header_line, fortran_format = rinex_labels()

    module_logger.debug(
        'Correct variables "{}" {}'.format(label, rinex_correction_dict[label])
    )
    line_structure = fortran_format[rinex_header_line.index(label)]
    fwriter = ff.FortranRecordWriter(line_structure)
    module_logger.debug("Format string: {}".format(fwriter.format))

    space_width = [int(item) for item in re.findall(r"[0-9]+", fwriter.format)]
    module_logger.debug("with list: {}".format(space_width))

    rinex_correction_dict[label].append(label)
    if label in rinex_dict.keys():
        module_logger.debug('to be corrected "{}" {}'.format(label, rinex_dict[label]))

    for item, width in zip(rinex_correction_dict[label], space_width):
        index = rinex_correction_dict[label].index(item)

        if not item:
            if label in rinex_dict.keys():
                fill_item = rinex_dict[label][index]
                rinex_correction_dict[label][index] = fill_item
                if not isinstance(fill_item, float) and not isinstance(fill_item, int):
                    right_spaces = " " * (width - len(rinex_dict[label][index]))
                    rinex_correction_dict[label][index] = (
                        rinex_dict[label][index] + right_spaces
                    )

        else:
            if not isinstance(item, float) and not isinstance(item, int):
                right_spaces = " " * (width - len(item))
                rinex_correction_dict[label][index] += right_spaces

    module_logger.info(
        'Correct variables "{}" {}'.format(label, rinex_correction_dict[label])
    )

    return fwriter.write(rinex_correction_dict[label])


def read_gzip_file(rfile, loglevel=logging.WARNING):
    """ """
    import gzip

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    try:
        with gzip.open(rfile, "rb") as f:
            file_content = f.read()
            module_logger.info("Opened: {}".format(rfile))
    except FileNotFoundError:
        module_logger.exception("File {} not found".format(rfile))
        return None
    except gzip.BadGzipFile:
        module_logger.error("File {} not a proper qzip file".format(rfile))
        return None

    return file_content.decode("utf-8")


def read_zzipped_file(rfile, loglevel=logging.WARNING):
    """
    reads a RINEX file from path rfile and returns the base file name, path  and the header of the rinex file.

    input:
        rfile: a filename of a rinex file
        loglevel: loglevel to use within the module
    output:
        unzipped file contend
    """

    from unlzw import unlzw

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    try:
        with open(rfile, "rb") as f:
            zipped_file_content = f.read()
            module_logger.info("Opened: {}".format(rfile))
    except FileNotFoundError:
        module_logger.exception("File {} not found".format(rfile))
        return None

    return unlzw(zipped_file_content).decode("utf-8")


def read_text_file(rfile, loglevel=logging.WARNING):
    """ """

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    try:
        with open(rfile, "r") as f:
            file_content = f.read()
            module_logger.info("Opened: {}".format(rfile))
    except FileNotFoundError:
        module_logger.exception("File {} not found".format(rfile))
        return None
    except gzip.BadGzipFile:
        module_logger.error("File {} not a proper qzip file".format(rfile))
        return None

    return file_content


def read_rinex_file(rfile, loglevel=logging.WARNING):
    """ """

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    if rfile.suffix == ".Z":
        rfile_content = read_zzipped_file(rfile, loglevel=logging.WARNING)
    elif rfile.suffix == ".gz":
        rfile_content = read_gzip_file(rfile, loglevel=logging.WARNING)
    else:
        module_logger.warning(
            "Unknown compression format {} on file {}".format(rfile.suffix, rfile)
        )
        rfile_content = read_text_file(rfile, loglevel=logging.WARNING)

    return rfile_content


def read_rinex_header(rfile, loglevel=logging.WARNING):
    """
    reads a RINEX file from path rfile and returns the base file name, path  and the header of the rinex file.

    input:
        rfile: a filename of a rinex file
        loglevel: loglevel to use within the module
    output:
        dictionary containing the file name and string containing the header section of the rinex file
    """
    import re
    import sys
    from pathlib import Path

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    rheader = None
    rfile = Path(rfile)
    module_logger.info("Path to rinex file: {}".format(rfile.parent))
    module_logger.info("Rinex file: {}".format(rfile.name))

    rfile_content = read_rinex_file(rfile, loglevel=logging.WARNING)

    if rfile_content:
        rheader = re.search(r"^.+(?:\n.+)+END OF HEADER", rfile_content).group()

    if not rheader:
        module_logger.warning(
            "Search for END OF HEADER did not return any result from the header of {}".format(
                rfile
            )
        )
        return None

    module_logger.debug("Rinex header: {}".format(rheader))

    return {"rinex file": [rfile.parent, rfile.name], "header": rheader}


def change_file_header(rheader, savedir=None):
    """ """

    import gzip
    import re
    from pathlib import Path

    rfile = Path(*rheader["rinex file"])
    rfile_content = read_rinex_file(rfile, loglevel=logging.WARNING)
    rfile_new_content = re.sub(
        r"^.+(?:\n.+)+END OF HEADER", rheader["header"], rfile_content
    )

    if savedir:
        rfile = Path(savedir, rfile.name)

    outfile = rfile.with_suffix(".gz")

    with gzip.open(outfile, "wb") as f:
        f.write(bytes(rfile_new_content, "utf-8"))


def main(level=logging.debug):
    """
    quering metadata from tos and comparing to relevant rinex files
    """
    import logging
    import re
    import sys
    from datetime import datetime, timedelta
    from pathlib import Path

    import pandas as pd

    import gps_metadata_functions as gpsf
    import tos

    # logging settings
    # logger = get_logger(name=__name__, level=logging.DEBUG)
    url_rest_tos = "https://vi-api.vedur.is/tos/v1"
    # print(module_logger.getEffectiveLevel())

    stationInfo_list = []
    rheader = []

    for sta in ["VMEY"]:  # , "AUST", "VMEY"]:

        station = gps_metadata(sta, url_rest_tos, loglevel=logging.WARNING)
        # print(station)
        # print(station['device_history'])
        # for item in station['device_history']:
        #     print(item['antenna'])
        #
        # gpsf.printStationHistory(station, raw_format=False, loglevel=logging.WARNING)

        stationInfo_list += gpsf.printStationInfo(station)
        for infoline in stationInfo_list:
            print(infoline)

        start = datetime(2002, 3, 29)
        end = datetime(2022, 4, 23)
        # session_nr = 0
        if station:
            session_list = fileList(
                station, start=None, end=None, loglevel=logging.WARNING
            )
            # for session in session_list:
            #    print(session)

            if session_list:
                session = session_list[-1]
                # print(session['session_number'])
                # print(gpsf.sessionsList(station))
                # rheader = read_rinex_header(session['filelist'][-1],loglevel=logging.WARNING)
        # rheader = get_header(read_zzipped_file("./RHOF0870.02D.Z", loglevel=logging.WARNING))
        # rheader = read_rinex_header("./RHOF0870.02D.Z",loglevel=logging.INFO)
        # rheader = read_gzip_file("./RHOF0870.02D.gz", loglevel=logging.WARNING)
        # rheader = read_rinex_header(session["filelist"][-1], loglevel=logging.WARNING)

        if rheader:
            rinex_dict = extract_from_rheader(rheader, loglevel=logging.WARNING)

            rinex_correction_dict = compare_TOS_to_rinex(
                rinex_dict,
                gpsf.getSession(station, session["session_number"]),
                loglevel=logging.INFO,
            )
        # rmqdict(rinex_dict, rinex_correction_dict)
        # rheader = fix_rinex_header(rinex_correction_dict, rinex_dict, rheader, loglevel=logging.WARNING)
        # print(rheader['rinex file'])
        # print(rheader['header'])
        # change_file_header(rheader,savedir=Path.cwd())

        # rfile_content = read_zzipped_file("./RHOF0870.02D.Z")
        # pattern = r"^.+(?:\n.+)+END OF HEADER"
        # mstring = re.compile(pattern)
        # result = mstring.search(rfile_content)
        # rfile_new = re.sub(mstring,rheader['header'],rfile_content)
        # print(rfile_new)
        # with open("tmp.txt", 'w') as f:
        #    f.write(rfile_new)
        # if rfile_new:

        #   #matched_line = result.group()
        #   print("{}".format(rfile_new))

        # sessions = gpsf.sessionsList(station)
        # print_attributes_string = "{:<19}  {:<19}  "
        # for session in sessions:
        #     print( print_attributes_string.format(*session) )

    # for line in stationInfo_list:
    #    print(line)


if __name__ == "__main__":
    main(level=logging.DEBUG)

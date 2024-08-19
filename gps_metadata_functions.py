#!/usr/bin/python3.1
#
# Project: gps_metadata_functions
# Authors: Benedikt Ǵunnar Ófeigsson
#          parts are edited TOSTools authored by Tryggvi Hjörvar
# Date: april 2022
#
#

import json
import logging
from datetime import datetime
from datetime import datetime as dt
from datetime import timedelta
from operator import itemgetter

import pandas as pd
from tabulate import tabulate

import gps_metadata_qc as gpsqc


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


def printStationHistory(station, raw_format=False, loglevel=logging.WARNING):
    """
    print station history
    """

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    station_headers = [key for key in station.keys() if key != "device_history"]
    station_attributes = tuple(
        value
        for key, value in station.items()
        if key not in ["contact", "device_history"]
    )
    module_logger.info("Station: {}".format(station))
    print(tabulate([station_attributes], headers=station_headers))
    contact_info = [
        (station["contact"][item]["role_is"], station["contact"][item]["name"])
        for item in station["contact"].keys()
    ]
    print(tabulate(contact_info, headers=["Hlutverk", "Nafn"]))
    print("-" * 100)
    device_list = ["gnss_receiver", "antenna", "monument", "radome"]
    print(
        " " * 42
        + "| {0}                                       | {1}                                     | {2}                         | {3}".format(
            *device_list
        )
    )

    headers_list = []
    devices_list = []
    device_types_list = []
    attributes_string_list = []

    for item in station["device_history"]:

        devices = [key for key in item.keys() if key not in ["time_from", "time_to"]]

        header_list = ["time_from", "time_to"]
        if item["time_from"] is None:
            time_from = "None"
        else:
            time_from = item["time_from"].strftime("%Y-%m-%d %H:%M:%S")

        if item["time_to"] is None:
            time_to = "None"
        else:
            time_to = item["time_to"].strftime("%Y-%m-%d %H:%M:%S")

        attributes_list = [time_from, time_to]

        print_attributes_string = "{:<19}  {:<19}  "
        print_header_string = "{:<19}  {:<19}  "

        for device in device_list:
            if device in item.keys():
                device_headers = [key for key in item[device].keys()]
                device_attributes = [value for key, value in item[device].items()]
                # make the labels nicer
                if device == "monument":
                    dev_index = device_headers.index("serial_number")
                    device_headers.remove("serial_number")
                    del device_attributes[dev_index]

                    dev_index = device_headers.index("model")
                    device_headers.remove("model")
                    del device_attributes[dev_index]

                if not raw_format:
                    if "antenna_height" in device_headers:
                        device_headers[device_headers.index("antenna_height")] = (
                            "Height"
                        )
                    if "antenna_reference_point" in device_headers:
                        device_headers[
                            device_headers.index("antenna_reference_point")
                        ] = "Ref."

                    if "monument_height" in device_headers:
                        device_headers[device_headers.index("monument_height")] = (
                            "Height"
                        )
                    if "monument_offset_north" in device_headers:
                        device_headers[
                            device_headers.index("monument_offset_north")
                        ] = "North"
                    if "monument_offset_east" in device_headers:
                        device_headers[device_headers.index("monument_offset_east")] = (
                            "East"
                        )

                    if "serial_number" in device_headers:
                        device_headers[device_headers.index("serial_number")] = "SN"
                    if "model" in device_headers:
                        device_headers[device_headers.index("model")] = "Model"
                    if "time_from" in device_headers:
                        device_headers[device_headers.index("time_from")] = "Start time"
                    if "time_to" in device_headers:
                        device_headers[device_headers.index("time_to")] = "End time"

                try:
                    for i, n in enumerate(device_attributes):
                        if n == None:
                            device_attributes[i] = "None"
                except:
                    pass

                if device == "gnss_receiver":
                    hstring = (
                        "| " + "{:14.14} " * (len(device_headers) - 1) + " {:5.5} "
                    )
                    string = "| " + "{:14.14} " * (len(device_headers) - 1) + " {:5.5} "
                elif device == "antenna":
                    hstring = "| " + "{:14.14} {:15.15} {:6.6} {:5.5} "
                    string = "| " + "{:14.14} {:15.15} {:>7.4f} {:5.5} "
                elif device == "monument":
                    hstring = "| " + "{:7.7} {:7.7} {:7.7}   "
                    string = "| " + "{:>7.4f} {:>7.4f} {:>7.4f}   "
                else:
                    string = "| " + "{} " * (len(device_headers)) + "  "

                print_header_string += hstring
                header_list += device_headers

                print_attributes_string += string
                attributes_list += device_attributes

        device_types_list.append(devices)
        attributes_string_list.append(print_attributes_string)
        headers_list.append(header_list)
        devices_list.append(attributes_list)

    # print(print_string)
    # print( print_header_string.format(*header_list) )
    # print( print_attributes_string.format(*attributes_list) )
    if raw_format:
        for devices, headers, values in zip(
            device_types_list, headers_list, devices_list
        ):
            print("+" * 240)
            print(tabulate([devices], tablefmt="plain"))
            print(tabulate([headers]))
            print(tabulate([values], tablefmt="plain"))
        print("+" * 240)
    else:
        # print(print_header_string)
        # print(headers_list)
        # print(print_header_string.format(*headers_list[0]))
        print("-" * 200)
        # print(attributes_string_list)
        for string, value in zip(attributes_string_list, devices_list):
            print(string)
            # print(string.format(*value))


def getSession(station, session_nr, loglevel=logging.WARNING):
    """ """

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    session = {key: value for key, value in station.items() if key != "device_history"}
    module_logger.info("Station information: {}".format(session))
    session["device_history"] = station["device_history"][session_nr]
    module_logger.info("session dictionary: {}".format(session))

    return session


def printStationInfo(station, loglevel=logging.WARNING):
    """ """

    # logging
    module_logger = get_logger(name=__name__, level=loglevel)

    header = "*SITE  Station Name      Session Start      Session Stop       Ant Ht   HtCod  Ant N    Ant E    Receiver Type         Vers                  SwVer  Receiver SN           Antenna Type     Dome   Antenna SN"
    # print(header)

    stationInfo_list = []
    for item in station["device_history"]:
        module_logger.debug(
            "item: %s", json.dumps(item, default=gpsqc.datetime_serializer, indent=2)
        )
        try:
            time_from = item["time_from"].strftime("%Y %j %H %M %S")
        except:
            module_logger.warning(
                "time_from has wrong type should be datetime, format is {0}: exiting program ...".format(
                    type(item["time_from"])
                )
            )
            quit()

        try:
            time_to = item["time_to"].strftime("%Y %j %H %M %S")
        except:
            time_to = "9999 999 00 00 00"

        # receiver type

        if "antenna" in item.keys():
            if item["antenna"]["model"] is None:
                antenna_type = "---------------"
            else:
                antenna_type = item["antenna"]["model"]

            # receiver sn
            if item["antenna"]["serial_number"] is None:
                antenna_SN = "---------------"
            else:
                antenna_SN = item["antenna"]["serial_number"]

            # Antenna height and offsets
            antenna_height = (
                item["antenna"]["antenna_height"] + item["monument"]["monument_height"]
            )
            antenna_N = item["monument"]["monument_offset_north"]
            antenna_E = item["monument"]["monument_offset_east"]

            if item["antenna"]["antenna_reference_point"] is None:
                antenna_reference_point = "-----"
            else:
                antenna_reference_point = item["antenna"]["antenna_reference_point"]

        else:
            antenna_height = 0.0000
            antenna_reference_point = "DHARP"
            antenna_N = 0.0000
            antenna_E = 0.0000
            antenna_type = "---------------"
            antenna_SN = "---------------"

        # receiver type
        if "gnss_receiver" in item.keys():
            if item["gnss_receiver"]["model"] is None:
                receiver_type = "--------------------"
            else:
                receiver_type = item["gnss_receiver"]["model"]

            # receiver SN
            if item["gnss_receiver"]["serial_number"] is None:
                receiver_SN = "--------------------"
            else:
                receiver_SN = item["gnss_receiver"]["serial_number"]

            # receiver firmware
            if item["gnss_receiver"]["firmware_version"] is None:
                firmware_version = "--------------------"
            else:
                firmware_version = item["gnss_receiver"]["firmware_version"]

            # receiver software
            if item["gnss_receiver"]["software_version"] is None:
                software_version = "-----"
            else:
                software_version = item["gnss_receiver"]["software_version"]
            # -------------------------------------------------------
        else:
            receiver_type = "--------------------"
            firmware_version = "--------------------"
            software_version = "-----"
            receiver_SN = "--------------------"

        # radome
        if "radome" in item.keys():
            dome = item["radome"]["model"]
        else:
            dome = "NONE"

        # header='*SITE  Station Name      Session Start      Session Stop       Ant Ht   HtCod  Ant N    Ant E    Receiver Type         Vers                  SwVer  Receiver SN           Antenna Type     Dome   Antenna SN'
        sessionLine = " {0:4.4}  {1:17.17} {2:17.17}  {3:17.17}  {4: 1.4f}  {5:5.5}  {6: 1.4f}  {7: 1.4f}  {8:20.20}  {9:20.20}  {10:>5.5}  {11:20.20}  {12:15.15}  {13:5.5}  {14:20.20}".format(
            station["marker"].upper(),
            station["name"][:18],
            time_from,
            time_to,
            antenna_height,
            antenna_reference_point,
            antenna_N,
            antenna_E,
            receiver_type[:21],
            firmware_version[:21],
            software_version[:6],
            receiver_SN[:21],
            antenna_type[:16],
            dome[:6],
            antenna_SN,
        )
        stationInfo_list.append(sessionLine)

    return stationInfo_list

    return session


def sessionsList(station, date_format="%Y-%m-%d %H:%M:%S"):
    """ """

    devices_list = []

    for item in station["device_history"]:
        if date_format:
            if item["time_from"] is None:
                time_from = "None"
            else:
                time_from = item["time_from"].strftime(date_format)

            if item["time_to"] is None:
                time_to = "None"
            else:
                time_to = item["time_to"].strftime(date_format)
        else:
            time_from = item["time_from"]
            time_to = item["time_to"]

        devices_list.append([time_from, time_to])

    return devices_list


def getStationList(subsets={}):
    """ """

    station_list = []
    keyorder = [
        "marker",
        "name",
        "date_from",
        "lon",
        "lat",
        "altitude",
        "operational_class",
        "date_to",
    ]
    stations = gpsqc.searchStation(
        "GPS stöð", code="subtype", domains="geophysical", loglevel=logging.WARNING
    )
    for station in stations:
        sta_dict = {}
        for attribute in station["attributes"]:
            if attribute["code"] in ["marker", "operational_class", "name"]:
                sta_dict[attribute["code"]] = attribute["value"]
                if attribute["code"] == "marker":
                    try:
                        sta_dict["date_from"] = datetime.strptime(
                            attribute["date_from"], "%Y-%m-%dT%H:%M:%S"
                        )
                    except:
                        sta_dict["date_from"] = None
                    try:
                        sta_dict["date_to"] = datetime.strptime(
                            attribute["date_to"], "%Y-%m-%dT%H:%M:%S"
                        )
                    except:
                        sta_dict["date_to"] = None

            elif attribute["code"] in ["lat", "lon", "altitude"]:
                sta_dict[attribute["code"]] = float(attribute["value"])
        station_list.append({k: sta_dict[k] for k in keyorder if k in sta_dict})

    if subsets:
        LMI_station_list = [
            "akur",
            "gusk",
            "heid",
            "hofn",
            "isaf",
            "myva",
            "reyk",
            "alhv",
            "bjtv",
        ]
        HI_station_list = ["krac", "gonh", "ste2", "syrf", "thrc"]
        uknown_station_list = ["s001", "7058"]
        remove_list = LMI_station_list + HI_station_list + uknown_station_list

        tmp_list = []
        for item in station_list:
            if item["marker"] not in remove_list:
                tmp_list.append(item)

        station_list[:] = tmp_list

    return station_list


def print_station_list(station_list, sortby="marker"):
    """ """

    station_list[:] = sorted(station_list, key=itemgetter(sortby))
    keylist = [
        "marker",
        "name",
        "date_from",
        "lon",
        "lat",
        "altitude",
        "operational_class",
        "date_to",
    ]
    value_list = [list(item.values()) for item in station_list]

    # print(tabulate(value_list, headers=keylist))

    return station_list


def count_GPS_stations(station_list):
    """ """

    station_list[:] = sorted(station_list, key=itemgetter("date_from"))

    station_count = []
    station_counter = 0
    yearly_addition = total_in_year = 0
    last_item = station_list[0]["date_from"]
    for item in station_list:
        if item["date_from"].year > last_item.year:
            yearly_addition = station_counter - total_in_year
            # print("Total number of stations {}:\t{} stations added in {}".format(station_counter,yearly_addition, last_item.year))
            total_in_year = station_counter
            station_count.append([last_item.year, station_counter, yearly_addition])

        station_counter += 1
        last_item = item["date_from"]
    else:
        yearly_addition = station_counter - total_in_year
        station_count.append([item["date_from"].year, station_counter, yearly_addition])
        # print("Total number of stations {}:\t{} of stations added in {}".format(station_counter,yearly_addition, item['date_from'].year))

    keylist = ["Year", "Total #", "New #"]
    print(tabulate(station_count, headers=keylist))


def grep_line_aslist(listf, text):
    """"""
    with open(listf, "r") as f:
        for line in f:
            if text in line:
                return line.split()
        else:
            return [text, ""]


def main():
    """ """

    # station_list = getStationList(subsets={"IMO": True})
    #
    # sorted_station_list = print_station_list(station_list, sortby="marker")
    # isgps = pd.DataFrame(sorted_station_list)
    # isgps.set_index("marker", inplace=True)
    # isgps["date_from"] = pd.to_datetime(isgps["date_from"], errors="coerce")
    # isgps = isgps[isgps["date_from"] < dt(2018, 1, 1)]
    # print(ISGPS[["name", "date_from", "lon", "lat"]])
    # isgps[["name", "date_from", "lon", "lat"]].to_csv("stations.list", sep="\t")

    # count_GPS_stations(station_list)

    antenna = "ASH701945C_M"
    antennaf = "antenna_arp.list"
    marker = "TREE"
    platefile = "./station-plate"
    print(grep_line_aslist(platefile, marker))


if __name__ == "__main__":
    main()

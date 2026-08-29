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
import sys
from datetime import datetime as dt
from datetime import timedelta
from operator import itemgetter
from pathlib import Path, PurePath

import pandas as pd
from gtimes import timefunc as tf
from gtimes.timefunc import datefRinex
from tabulate import tabulate

# Import legacy module (transitioning)
from . import gps_metadata_qc as gpsqc
from .io.formatters import json_print

# Import new modular components
from .utils.logging import get_logger


def get_data_file_path(filename):
    """Absolute path to a ``data/station_config/`` file, checkout or wheel.

    Delegates to :func:`tostools.data_files.data_path` — repo root first (a
    source checkout's edits must win), packaged copy second. The old
    ``Path(__file__).parent…`` arithmetic hit ``<venv>/lib/pythonX.Y`` for a
    wheel install, so these files were unreachable off a dev box.
    """
    from .data_files import data_path

    return str(data_path("station_config", filename))


def print_station_history(station, raw_format=False, loglevel=logging.WARNING):
    """
    print station history
    """

    # logging settings
    module_logger = get_logger(__name__, loglevel)

    station_headers = [key for key in station.keys() if key != "device_history"]
    station_attributes = tuple(
        value
        for key, value in station.items()
        if key not in ["contact", "device_history"]
    )
    # Log concise station summary instead of full dictionary
    station_name = station.get("name", station.get("marker", "unknown"))
    coords = f"({station.get('lat', 'N/A')}, {station.get('lon', 'N/A')})"
    device_count = len(station.get("device_history", []))
    module_logger.debug(
        f"Processing station: {station_name} at {coords} with {device_count} device sessions"
    )
    module_logger.debug("Full station data: {}".format(station))
    print(tabulate([station_attributes], headers=station_headers))
    contact_info = [
        (
            station["contact"][item]
            .get("role", station["contact"][item]["role_is"])
            .title(),
            station["contact"][item]["name"],
        )
        for item in station["contact"].keys()
    ]
    print(tabulate(contact_info, headers=["Role", "Name"]))
    print("-" * 100)
    device_list = ["gnss_receiver", "antenna", "monument", "radome"]
    print(
        " " * 42
        + f"| {device_list[0]}"
        + " " * 39
        + f"| {device_list[1]}"
        + " " * 38
        + f"| {device_list[2]}"
        + " " * 18
        + f"| {device_list[3]}"
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
                device_headers = list(key for key in item[device].keys())
                device_attributes = [value for _, value in item[device].items()]
                # make the labels nicer
                if device == "monument":
                    module_logger.debug("device_headers: %s", device_headers)
                    dev_index = device_headers.index("serial_number")
                    device_headers.remove("serial_number")
                    del device_attributes[dev_index]

                    # dev_index = device_headers.index("model")
                    # device_headers.remove("model")
                    # del device_attributes[dev_index]

                if raw_format is False:
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
                        device_headers[device_headers.index("serial_number")] = (
                            "Serial Number"
                        )
                    if "model" in device_headers:
                        device_headers[device_headers.index("model")] = "Model"
                    if "time_from" in device_headers:
                        device_headers[device_headers.index("time_from")] = "Start time"
                    if "time_to" in device_headers:
                        device_headers[device_headers.index("time_to")] = "End time"

                try:
                    for i, n in enumerate(device_attributes):
                        if n is None:
                            device_attributes[i] = "None"
                except:
                    pass

                if device == "gnss_receiver":
                    hstring = (
                        "| " + "{:14.14} " * (len(device_headers) - 1) + " {:5.5} "
                    )
                    string = "| " + "{:14.14} " * (len(device_headers) - 1) + " {:5.5} "
                elif device == "antenna":
                    hstring = "| " + "{:14.14} {:15.15} {:>7.4} {:>7.4} {:>7.4} {:5.5} "
                    string = (
                        "| " + "{:14.14} {:15.15} {:>7.4f} {:>7.4f} {:>7.4f} {:5.5} "
                    )
                elif device == "monument":
                    hstring = "| " + "{:25.25} {:7.7} {:7.7} {:7.7}   "
                    string = "| " + "{:25.25} {:>7.4f} {:>7.4f} {:>7.4f}   "
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
        print("+" * 200)
        for devices, headers, values in zip(
            device_types_list, headers_list, devices_list
        ):
            print(tabulate([devices], tablefmt="plain"))
            # print(tabulate([headers]))
            print(tabulate([values], tablefmt="fancy"))
        print("+" * 200)
    else:
        # Use simple tabulate format for regular output - avoiding string formatting bugs
        print("-" * 200)
        for devices, headers, values in zip(
            device_types_list, headers_list, devices_list
        ):
            print(f"Device types: {', '.join(devices)}")
            # Convert all values to strings to avoid formatting issues
            str_values = [str(v) for v in values]
            print(tabulate([str_values], headers=headers, tablefmt="simple"))
            print("-" * 100)


def getSession(station, session_nr, loglevel=logging.WARNING):
    """ """

    # logging
    module_logger = get_logger(__name__, loglevel)

    session = {key: value for key, value in station.items() if key != "device_history"}
    module_logger.info("Station information: {}".format(session))
    session["device_history"] = station["device_history"][session_nr]
    module_logger.info("session dictionary: {}".format(session))

    return session


def print_station_info(*args, **kwargs):
    """Delegator to the LIVE implementation in :mod:`tostools.legacy.gps_metadata_functions`.

    F2, same reasoning as :func:`site_log` above. The live copy is the LEGACY
    one — ``tosGPS`` reaches it at four call sites; the 256-line implementation
    that stood here had none, and the only test touching it
    (``tests/test_tostool.py``) is a permanently-skipped manual smoke test.

    Its signature could not have served the live call sites either:
    ``tosGPS.py:2070`` passes ``skip_validation=True``, a parameter only the
    legacy copy accepts.

    This matters more than the line count suggests — ``print_station_info``
    emits GAMIT ``station.info`` records, an externally consumed artefact like
    the site log. Unifying onto the copy production actually runs is what stops
    a future fix landing on the dead one.
    """
    from .legacy.gps_metadata_functions import print_station_info as _live

    return _live(*args, **kwargs)


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
    stations = gpsqc.search_station(
        "GPS stöð", code="subtype", domains="geophysical", loglevel=logging.WARNING
    )
    for station in stations:
        sta_dict = {}
        for attribute in station["attributes"]:
            if attribute["code"] in ["marker", "operational_class", "name"]:
                sta_dict[attribute["code"]] = attribute["value"]
                if attribute["code"] == "marker":
                    try:
                        sta_dict["date_from"] = dt.strptime(
                            attribute["date_from"], "%Y-%m-%dT%H:%M:%S"
                        )
                    except:
                        sta_dict["date_from"] = None
                    try:
                        sta_dict["date_to"] = dt.strptime(
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
    [list(item.values()) for item in station_list]

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


def get_radome(device_iter, date_from, date_to, loglevel=logging.WARNING):
    """
    return monument_height for given interval
    """

    module_logger = get_logger(__name__, loglevel)
    # NOTE: default radome is NONE
    antenna_radome = "NONE"
    antenna_radome_serial = ""

    print("\n", file=sys.stderr)
    for item in device_iter:
        module_logger.debug("item: \n%s", json_print(item))
        device = item["device"]
        session_start = device["date_from"]
        session_end = device["date_to"]
        module_logger.debug("-" * 50)
        module_logger.debug("date input: %s - %s", date_from, date_to)
        module_logger.debug("current session: %s - %s", session_start, session_end)

        if date_to:
            if date_to > session_start:
                if session_end and date_from > session_end:
                    pass
                else:
                    antenna_radome = device["model"]
                    module_logger.debug("model: %s", antenna_radome)
        else:
            if session_end and session_end < date_from:
                pass
            else:
                if date_from >= session_start:
                    antenna_radome = device["model"]
                    module_logger.debug("model: %s", antenna_radome)

    module_logger.debug("%s", "+" * 50)

    return antenna_radome, antenna_radome_serial


def get_monument_height(device_iter, date_from, date_to, loglevel=logging.WARNING):
    """
    return monument_heigt for given interval
    """

    module_logger = get_logger(__name__, loglevel)
    # NOTE: monument_height defaults to 0.0
    monument_height = 0.0

    print("", file=sys.stderr)
    for item in device_iter:
        module_logger.debug("monument_item: \n%s", json_print(item))
        device = item["device"]
        session_start = device["date_from"]
        session_end = device["date_to"]
        module_logger.debug("date_to: %s ", date_to)
        module_logger.debug("-" * 50)
        module_logger.debug("date input: %s - %s", date_from, date_to)
        module_logger.debug("current session: %s - %s", session_start, session_end)

        if date_to:
            if date_to > session_start:
                if session_end and date_from > session_end:
                    pass
                else:
                    monument_height = float(device["monument_height"])
                    module_logger.debug(
                        "monument_height: %s", device["monument_height"]
                    )
        else:
            if session_end and session_end < date_from:
                pass
            else:
                if date_from >= session_start:
                    monument_height = float(device["monument_height"])
                    module_logger.debug(
                        "monument_height: %s", device["monument_height"]
                    )

    module_logger.debug("%s", "+" * 50)

    return monument_height


def site_log(*args, **kwargs):
    """Delegator to the LIVE renderer in :mod:`tostools.legacy.gps_metadata_functions`.

    F2 (docs/architecture/legacy-fork-unification-plan.md). This module and its
    ``legacy/`` counterpart are a drifted fork, and for ``site_log`` the live
    copy is the LEGACY one — reached by ``core.site_log.build_site_log``, the
    single entry point behind both publishers (``tosGPS sitelog`` and receivers'
    ``epos-disseminate --sitelog``).

    The 612-line implementation that stood here had **no caller and no route to
    one**: not imported by any module in this package, absent from
    ``__init__._LAZY_EXPORTS``, unreachable via the ``_STAR_SOURCE`` fallback
    (``gps_rinex`` never binds the name), and with no importer in any editable
    sibling of the ``gpslibrary`` env or in ``~/git``. It also could not have
    served the live call site if reached: its signature accepted none of
    ``report_type`` / ``previous_log`` / ``agencies`` / ``monument_number``, so
    ``build_site_log``'s call raises ``TypeError`` against it — which
    ``scripts/dev/mutate_sitelog_oracle.py`` pins as mutation #10.

    Delegating rather than deleting keeps the name resolvable for anything
    reaching it dynamically, and forwards the WIDER legacy signature so this is
    a strict superset of what stood here.

    The import is function-local on purpose: ``legacy`` imports
    ``gps_metadata_qc``, which imports THIS module, so a module-level import
    would be circular.
    """
    from .legacy.gps_metadata_functions import site_log as _live

    return _live(*args, **kwargs)


def domes_info_form(station_identifier, loglevel=logging.WARNING):
    """
    print domes info form
    """

    module_logger = get_logger(__name__, loglevel)

    module_logger.info(station_identifier)

    # station = gps_metadata(station_identifier, url_rest_tos, loglevel=logging.CRITICAL)
    station, devices_history = gpsqc.get_station_metadata(
        station_identifier, gpsqc.URL_REST_TOS, loglevel=loglevel
    )
    gpsqc.get_device_sessions(devices_history, gpsqc.URL_REST_TOS, loglevel=loglevel)

    # devices_used = ["gnss_receiver", "antenna", "radome", "monument"]
    module_logger.info("station: %s", json_print(station))

    # DOMES INFORMATION FORM (DIF)

    # 1. Request from (full name) : Mr. Thorarinn Sigurdsson
    #     Agency                   : National Land Survey of Iceland
    #     E-mail                   : thorarinn.sigurdsson@lmi.is or lmi@lmi.is
    #     Date                     : 28.10.2021
    #
    # 2. Site Name                 : Fiflholt
    # 3. Country                   : Iceland
    # 4. Point Description         : The station is at the east site of Iceland on the
    #                              : North America tectonic plate. The antenna is mounted
    #                              : on a stainless steel quadripod, that is bolted
    #                              : and cemented into stable bedrock. The top of
    #                              : the quadripod is the ARP.
    #
    #  5. DOMES Number             :
    #  6. Local Number             : FIHO
    #  7. 4-Char Code              :
    #  8. Approximate Position
    #     Latitude (deg min)       : 064° 41.661'
    #     Longitude (deg min)      : 337° 51.121'
    #     Elevation (m)            : 125.2 m
    #  9. Instrument               : Rec.: Trimble NetR5, serial nr. 4806K53396
    #                  : Ant.: Navxperience 3G+C, serial nr. NA02473
    #
    #
    # 10. Date of Installation     : 18.06.2021
    # 11. Operation Contact Name   : Mr. Thorarinn Sigurdsson
    #     Agency                   : National Land Survey of Iceland
    #     E-mail                   : thorarinn.sigurdsson@lmi.is
    # 12. Site Contact Name        : Same as the operation contact person
    #     Agency                   :
    #     E-mail                   :


def file_list(
    station,
    pdir,
    start=None,
    end=None,
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

    # logging settings
    module_logger = get_logger(__name__, loglevel)

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
            flist = tf.datepathlist(
                formatString, "1D", time_from, time_to, closed="left"
            )
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


# NOTE: extra functions (using centralized logger now)


def grep_line_aslist(listf, text):
    """
    grep a line from list
    """
    with open(listf, "r") as f:
        for line in f:
            if text in line:
                return line.split()
        else:
            return [text, ""]


def json_print(json_struct):
    """
    print json nicely
    """
    return json.dumps(json_struct, cls=CustomeJSONEncoder, indent=2)


class CustomeJSONEncoder(json.JSONEncoder):
    """
    encoder for dealing with posixpath in json.dumps
    """

    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, dt):
            return obj.isoformat()
        # Let the base class default method raise the TypeError
        return super().default(obj)


def main():
    """ """

    station_list = getStationList()

    sorted_station_list = print_station_list(station_list, sortby="marker")
    ISGPS = pd.DataFrame(sorted_station_list)
    ISGPS.set_index("marker", inplace=True)
    # isgps["date_from"] = pd.to_datetime(isgps["date_from"], errors="coerce")
    # isgps = isgps[isgps["date_from"] < dt(2018, 1, 1)]
    print(ISGPS[["name", "date_from", "lon", "lat"]])
    ISGPS[["name", "date_from", "lon", "lat"]].to_csv("stations.list", sep="\t")

    # count_GPS_stations(station_list)

    # marker = "TREE"
    # platefile = "./station-plate"
    # print(grep_line_aslist(platefile, marker))


if __name__ == "__main__":
    main()

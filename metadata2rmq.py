#!/usr/bin/python3.1
#
# Project: gps_metadata2rmq
# Authors: Benedikt Gunnar Ófeigsson
#          parts edited TOSTools authored by Tryggvi Hjörvar
# Date: aug 2022
#
#

import logging
import json

import gps_metadata_functions as gpsf

url_rest_tos = "https://vi-api.vedur.is:11223/tos/v1"


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


def rmqdict(station_identifier, url_rest, loglevel=logging.WARNING):
    """
    prepearing for inserting metadata state into rabbitMQ
    """

    import gps_metadata_qc as qc
    from gtimes.timefunc import currDatetime

    # logging settings
    module_logger = get_logger(name=__name__, level=loglevel)

    station_metadata = qc.gps_metadata(
        station_identifier, url_rest, loglevel=logging.WARNING
    )
    module_logger.info(station_metadata)

    start = currDatetime(-1)
    session_list = qc.fileList(
        station_metadata, start=start, end=None, loglevel=logging.WARNING
    )
    session = session_list[-1]
    rheader = qc.read_rinex_header(session["filelist"][-1], loglevel=logging.WARNING)
    if rheader:
        rinex_dict = qc.extract_from_rheader(rheader, loglevel=logging.WARNING)

    rinex_correction_dict = qc.compare_TOS_to_rinex(
        rinex_dict,
        gpsf.getSession(station_metadata, session["session_number"]),
        loglevel=logging.WARNING,
    )

    return rinex_dict, rinex_correction_dict


def station_check(station_identifier):
    """
    return dictionary for rabbitMQ
    """

    from datetime import datetime as dt

    station = {}
    station["station_identifier"] = station_identifier.lower()
    station["sensor_location"] = "metadata"
    station["sensor_identifier"] = "gps"
    station["observation_time"] = dt.now()
    station["monitoring"] = {"passed": [], "caught": []}

    return station


def check_for_conflict(rinex_correction_dict, rinex_dict):
    """
    check if conflict and pass the result
    """

    from pathlib import Path
    import gtimes.timefunc as gt

    rinex_file = rinex_correction_dict.pop("rinex file")
    observation_time = gt.datefRinex([rinex_file[1]])
    rinex_file_path = Path(rinex_file[0], rinex_file[1])

    result = {"passed": [], "caught": []}
    check = {
        "monitoring.quality.gps.metadata.consistency.rinex_tos_conflict": {
            "severity": "critical",
            "observation_time": observation_time,
            "output": "Rinex file:\n {0}".format(rinex_file_path)
            + "Rinex file: {0}".format(rinex_correction_dict),
        },
    }

    if rinex_correction_dict:
        result["caught"].append(check)
    else:
        result["passed"].append(check)

    return result


class JSONCustomEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects"""

    def default(self, obj):

        import json
        from datetime import datetime

        if isinstance(obj, datetime):

            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)


def main(level=logging.WARNING):
    """
    sending metatata issues to rabbitMQ
    """

    import pika
    import configparser
    import json

    station_checks = {}
    for sta in ["kvis", "tanc", "vonc", "rhof"]:  # , "RHOF"]:
        rinex_dict, rinex_correction_dict = rmqdict(
            sta, url_rest_tos, loglevel=logging.WARNING
        )
        if sta not in station_checks:
            station_checks[sta] = station_check(sta)

        check_result = check_for_conflict(rinex_correction_dict, rinex_dict)
        station_checks[sta]["monitoring"]["caught"] = check_result["caught"]
        station_checks[sta]["monitoring"]["passed"] = check_result["passed"]

    print("=" * 60)
    print(station_checks)

    # Read configuration file
    config = configparser.ConfigParser()
    config.read("./config.cfg")

    credentials_user = config.get("RabbitMQ", "credentials_user")
    credentials_password = config.get("RabbitMQ", "credentials_password")
    rabbitmq_host = config.get("RabbitMQ", "rabbitmq_host")

    # Set up RabbitMQ channel connection
    credentials = pika.PlainCredentials(credentials_user, credentials_password)
    parameters = pika.ConnectionParameters(rabbitmq_host, 5672, "/", credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    for station_identifier, station in station_checks.items():
        if len(station["monitoring"]["caught"]) > 0:
            # print(json.dumps(station,cls=JSONCustomEncoder))
            channel.basic_publish(
                exchange="monitoring",
                routing_key="quality.gps." + station["station_identifier"] +
                            ".caught",
                body=json.dumps(station, cls=JSONCustomEncoder),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                ),
            )
        if len(station["monitoring"]["passed"]) > 0:
            # print(json.dumps(station,cls=JSONCustomEncoder))
            channel.basic_publish(
                exchange="monitoring",
                routing_key="quality.gps." + station["station_identifier"] +
                            ".passed",
                body=json.dumps(station, cls=JSONCustomEncoder),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                ),
            )

    connection.close()


if __name__ == "__main__":
    main(level=logging.DEBUG)

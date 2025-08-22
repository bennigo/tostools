import json
from datetime import datetime


def json_to_ascii(json_file, ascii_file):
    # Read JSON data
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    site_logs = []

    for site_info in data:
        # Extract relevant information
        print("Extracting site information...")
        site_name = site_info.get("name", "N/A")
        marker = site_info.get("marker", "N/A")
        iers_domes = site_info.get("iers_domes", "N/A")
        cdp_num = site_info.get("cdp_num", "N/A")
        monument = site_info.get("monument", {})
        monument_description = monument.get("description", "N/A")
        foundation = monument.get("foundation", "N/A")
        foundation_depth = monument.get("foundation_depth", "N/A")
        date_installed = site_info.get("date_from", "N/A")
        geological = site_info.get("geological", {})
        bedrock_type = geological.get("bedrock", {}).get("type", "N/A")
        bedrock_condition = geological.get("bedrock", {}).get("condition", "N/A")
        fracture_spacing = geological.get("fracture_spacing", "N/A")
        fault_zone = geological.get("fault_zone", "N/A")
        location = site_info.get("location", {})
        city = location.get("city", "N/A")
        state = location.get("state", "N/A")
        country = location.get("country", "N/A")
        tectonic_plate = location.get("tectonic", {}).get("plate_name", "N/A")
        coordinates = location.get("coordinates", {})
        x_coordinate = coordinates.get("X", "N/A")
        y_coordinate = coordinates.get("Y", "N/A")
        z_coordinate = coordinates.get("Z", "N/A")
        latitude = coordinates.get("lat", "N/A")
        longitude = coordinates.get("lon", "N/A")
        elevation = coordinates.get("alt", "N/A")

        print(f"Site Name: {site_name}, Marker: {marker}")

        # Extract contact information
        print("Extracting contact information...")
        contacts = site_info.get("station_contacts", [])
        contact_details = []
        for contact in contacts:
            contact_info = contact.get("contact", {})
            contact_name = contact_info.get("name", "N/A")
            contact_role = contact_info.get("role", "N/A")
            contact_agency = contact_info.get("agency", {}).get("name", "N/A")
            contact_details.append(
                f"Contact Name: {contact_name}, Role: {contact_role}, Agency: {contact_agency}"
            )
            print(
                f"Contact: {contact_name}, Role: {contact_role}, Agency: {contact_agency}"
            )

        contact_details_str = "\n".join(contact_details)

        # Extract receiver information
        print("Extracting receiver information...")
        receiver_info = ""
        for item in site_info.get("station_items", []):
            print(f"Checking station item: {item}")
            item_type = item["item"].get("item_type", {}).get("name")
            print(f"Item type: {item_type}")
            if item_type == "receiver":
                receiver_item = item.get("item", {})
                receiver_type = next(
                    (
                        attr.get("value_varchar")
                        for attr in receiver_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name") == "model"
                    ),
                    "N/A",
                )
                serial_number = next(
                    (
                        attr.get("value_varchar")
                        for attr in receiver_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name") == "serial_number"
                    ),
                    "N/A",
                )
                date_installed_rcvr = receiver_item.get("date_from", "N/A")
                date_removed_rcvr = receiver_item.get("date_to", "N/A")
                receiver_info += (
                    f"3.x  Receiver Type            : {receiver_type}\n"
                    f"     Satellite System         : \n"
                    f"     Serial Number            : {serial_number}\n"
                    f"     Firmware Version         : \n"
                    f"     Elevation Cutoff Setting : \n"
                    f"     Date Installed           : {date_installed_rcvr}\n"
                    f"     Date Removed             : {date_removed_rcvr}\n"
                    f"     Temperature Stabiliz.    : \n"
                    f"     Additional Information   : \n\n"
                )
                # Debugging output
                print(f"Receiver Type: {receiver_type}")
                print(f"Serial Number: {serial_number}")
                print(f"Date Installed: {date_installed_rcvr}")
                print(f"Date Removed: {date_removed_rcvr}")

        # Extract antenna information
        print("Extracting antenna information...")
        antenna_info = ""
        for item in site_info.get("station_items", []):
            print(f"Checking station item: {item}")
            item_type = item["item"].get("item_type", {}).get("name")
            print(f"Item type: {item_type}")
            if item_type == "antenna":
                antenna_item = item.get("item", {})
                antenna_type = next(
                    (
                        attr.get("value_varchar")
                        for attr in antenna_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name") == "model"
                    ),
                    "N/A",
                )
                serial_number = next(
                    (
                        attr.get("value_varchar")
                        for attr in antenna_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name") == "serial_number"
                    ),
                    "N/A",
                )
                arp = next(
                    (
                        attr.get("value_varchar")
                        for attr in antenna_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name")
                        == "antenna_reference_point"
                    ),
                    "N/A",
                )
                antenna_height = next(
                    (
                        attr.get("value_varchar")
                        for attr in antenna_item.get("item_attributes", [])
                        if attr.get("attribute", {}).get("name") == "antenna_height"
                    ),
                    "N/A",
                )
                date_installed_ant = antenna_item.get("date_from", "N/A")
                date_removed_ant = antenna_item.get("date_to", "N/A")
                antenna_info += (
                    f"4.x  Antenna Type             : {antenna_type}\n"
                    f"     Serial Number            : {serial_number}\n"
                    f"     Antenna Reference Point  : {arp}\n"
                    f"     Marker->ARP Up Ecc. (m)  : {antenna_height}\n"
                    f"     Marker->ARP North Ecc(m) : \n"
                    f"     Marker->ARP East Ecc(m)  : \n"
                    f"     Alignment from True N    : \n"
                    f"     Antenna Radome Type      : \n"
                    f"     Radome Serial Number     : \n"
                    f"     Antenna Cable Type       : \n"
                    f"     Antenna Cable Length     : \n"
                    f"     Date Installed           : {date_installed_ant}\n"
                    f"     Date Removed             : {date_removed_ant}\n"
                    f"     Additional Information   : \n\n"
                )
                # Debugging output
                print(f"Antenna Type: {antenna_type}")
                print(f"Serial Number: {serial_number}")
                print(f"ARP: {arp}")
                print(f"Antenna Height: {antenna_height}")
                print(f"Date Installed: {date_installed_ant}")
                print(f"Date Removed: {date_removed_ant}")

        # Format the data into ASCII/UTF-8 string
        print("Formatting data into ASCII/UTF-8 string...")
        ascii_content = (
            f"XXXX Site Information Form (site log)\n"
            f"    International GNSS Service\n"
            f"    See Instructions at:\n"
            f"      https://files.igs.org/pub/station/general/sitelog_instr.txt\n\n"
            f"0.   Form\n\n"
            f"     Prepared by (full name)  : \n"
            f"     Date Prepared            : {datetime.now().strftime('%Y-%m-%d')}\n"
            f"     Report Type              : NEW\n"
            f"     If Update:\n"
            f"      Previous Site Log       : \n"
            f"      Modified/Added Sections : \n\n"
            f"1.   Site Identification of the GNSS Monument\n\n"
            f"     Site Name                : {site_name}\n"
            f"     Four Character ID        : {marker}\n"
            f"     Monument Inscription     : {monument_description}\n"
            f"     IERS DOMES Number        : {iers_domes}\n"
            f"     CDP Number               : {cdp_num}\n"
            f"     Monument Description     : {monument_description}\n"
            f"       Height of the Monument : \n"
            f"       Monument Foundation    : {foundation}\n"
            f"       Foundation Depth       : {foundation_depth}\n"
            f"     Marker Description       : {marker}\n"
            f"     Date Installed           : {date_installed}\n"
            f"     Geologic Characteristic  : \n"
            f"       Bedrock Type           : {bedrock_type}\n"
            f"       Bedrock Condition      : {bedrock_condition}\n"
            f"       Fracture Spacing       : {fracture_spacing}\n"
            f"       Fault zones nearby     : {fault_zone}\n"
            f"         Distance/activity    : \n"
            f"     Additional Information   : \n\n"
            f"2.   Site Location Information\n\n"
            f"     City or Town             : {city}\n"
            f"     State or Province        : {state}\n"
            f"     Country                  : {country}\n"
            f"     Tectonic Plate           : {tectonic_plate}\n"
            f"     Approximate Position (ITRF)\n"
            f"       X coordinate (m)       : {x_coordinate}\n"
            f"       Y coordinate (m)       : {y_coordinate}\n"
            f"       Z coordinate (m)       : {z_coordinate}\n"
            f"       Latitude (N is +)      : {latitude}\n"
            f"       Longitude (E is +)     : {longitude}\n"
            f"       Elevation (m,ellips.)  : {elevation}\n"
            f"     Additional Information   : \n\n"
            f"{receiver_info}"
            f"{antenna_info}"
            f"Contacts:\n{contact_details_str}\n"
            f"----------------------------------------\n"
        )

        print(json.dumps(site_info, indent=2))
        site_logs.append(ascii_content)

    # Write to ASCII file
    print("Writing to ASCII file...")
    with open(ascii_file, "w", encoding="utf-8") as f:
        f.write("\n".join(site_logs))
    print("Done writing to ASCII file.")


def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert JSON station data to ASCII format')
    parser.add_argument('json_file', help='Input JSON file path')
    parser.add_argument('ascii_file', help='Output ASCII file path')
    
    args = parser.parse_args()
    json_to_ascii(args.json_file, args.ascii_file)


if __name__ == "__main__":
    main()

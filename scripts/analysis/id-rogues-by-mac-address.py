#!/usr/bin/env python3
"""
Identify likely rogue access points by MAC OUI analysis
"""

# MAC OUI database (first 6 characters identify manufacturer)
consumer_vendors = [
    "NETGEAR",
    "TP-LINK",
    "Linksys",
    "ASUS",
    "D-Link",
    "Belkin",
    "Buffalo",
    "TRENDnet",
    "Huawei",
]

industrial_vendors = [
    "Cisco",
    "Hirschmann",
    "Moxa",
    "Phoenix Contact",
    "Siemens",
    "Rockwell",
    "Schneider Electric",
]


def analyse_access_points(survey_csv):
    """
    Analyse wireless survey results for suspicious APs
    """

    rogues = []
    suspicious = []
    authorised = []

    # Parse airodump-ng CSV output
    with open(survey_csv) as f:
        lines = f.readlines()

    # Find AP section (before client section)
    ap_section = []
    for line in lines:
        if "Station MAC" in line:
            break
        ap_section.append(line)

    print("[*] Rogue Access Point Detection")
    print("[*] Analysis of wireless survey results\n")

    for line in ap_section[2:]:  # Skip header lines
        if not line.strip():
            continue

        parts = line.split(",")
        if len(parts) < 14:
            continue

        bssid = parts[0].strip()
        power = parts[8].strip()
        essid = parts[13].strip()

        # Check if MAC indicates consumer device
        # In reality, you'd look up the OUI in a database
        is_consumer = any(
            vendor.lower() in bssid.lower() for vendor in consumer_vendors
        )

        is_industrial = any(
            vendor.lower() in bssid.lower() for vendor in industrial_vendors
        )

        if is_consumer:
            rogues.append(
                {
                    "bssid": bssid,
                    "essid": essid,
                    "power": power,
                    "reason": "Consumer-grade MAC address",
                }
            )
        elif not is_industrial and "UU_" not in essid:
            suspicious.append(
                {
                    "bssid": bssid,
                    "essid": essid,
                    "power": power,
                    "reason": "Unknown vendor, suspicious ESSID",
                }
            )

    print(f"[!] Found {len(rogues)} likely rogue access points:")
    for rogue in rogues:
        print(f"\n    ESSID: {rogue['essid']}")
        print(f"    BSSID: {rogue['bssid']}")
        print(f"    Signal: {rogue['power']} dBm")
        print(f"    Reason: {rogue['reason']}")

    print(
        f"\n[!] Found {len(suspicious)} suspicious access points requiring investigation"
    )

    return rogues, suspicious


if __name__ == "__main__":
    analyse_access_points("site_survey-01.csv")

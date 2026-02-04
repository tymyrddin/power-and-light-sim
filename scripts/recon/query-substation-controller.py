#!/usr/bin/env python3
"""
Query Substation Controller - Raw TCP SYN Probe
Tests if DNP3 port is open using raw TCP SYN packet
"""

from scapy.layers.inet import IP, TCP
from scapy.sendrecv import sr1

# Simulator: Substation RTU 1 on localhost:20000 (DNP3)
print("[*] Sending SYN probe to 127.0.0.1:20000 (DNP3)...")

pkt = IP(dst="127.0.0.1") / TCP(dport=20000, flags="S")
resp = sr1(pkt, timeout=2, verbose=False)

if resp:
    if resp.haslayer(TCP):
        flags = resp[TCP].flags
        if flags == 0x12:  # SYN-ACK
            print("[+] Port 20000 OPEN (SYN-ACK received)")
        elif flags == 0x14:  # RST-ACK
            print("[-] Port 20000 CLOSED (RST-ACK received)")
        else:
            print(f"[?] Port 20000 responded with flags: {flags}")
    print(f"[*] Response: {resp.summary()}")
else:
    print("[-] No response (filtered or host down)")

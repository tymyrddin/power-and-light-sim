#!/usr/bin/env python3
"""
Generate self-signed certificates for OPC UA servers.

Usage:
    python tools/generate_opcua_certificates.py              # Generate for all OPC UA servers
    python tools/generate_opcua_certificates.py --server scada_server_primary
    python tools/generate_opcua_certificates.py --list        # List OPC UA servers
    python tools/generate_opcua_certificates.py --force       # Overwrite existing certs

Discovers OPC UA servers from config/devices.yml and reads settings
from config/opcua_security.yml. Creates certificates in the certs/ directory.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cryptography.hazmat.primitives import serialization

from components.security.encryption import CertificateInfo, CertificateManager
from config.config_loader import ConfigLoader


def discover_opcua_servers(config: dict) -> list[dict]:
    """Discover all OPC UA servers from device configuration."""
    servers = []
    for device in config.get("devices", []):
        protocols = device.get("protocols", {})
        if "opcua" in protocols:
            servers.append(
                {
                    "name": device["name"],
                    "description": device.get("description", ""),
                    "zone": device.get("zone", "unknown"),
                    "opcua_config": protocols["opcua"],
                }
            )
    return servers


async def generate_cert_for_server(
    cert_manager: CertificateManager,
    certs_dir: Path,
    server_name: str,
    description: str,
    key_size: int,
    validity_hours: float,
    force: bool = False,
) -> bool:
    """Generate certificate for a single server. Returns True if generated."""
    cert_path = certs_dir / f"{server_name}.crt"
    key_path = certs_dir / f"{server_name}.key"

    if cert_path.exists() and key_path.exists() and not force:
        print(
            f"  Skipping {server_name} (certificate exists, use --force to overwrite)"
        )
        return False

    print(f"Generating certificate for: {server_name}")
    if description:
        print(f"  Description: {description}")

    certificate, private_key = cert_manager.generate_self_signed_cert(
        common_name=server_name,
        organization="Unseen University Power & Light Co.",
        validity_hours=validity_hours,
        key_size=key_size,
    )

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(cert_pem)

    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(key_pem)

    cert_info = CertificateInfo.from_x509(certificate)

    print(f"  Certificate: {cert_path}")
    print(f"  Private Key: {key_path}")
    print(f"  Key Size: {key_size} bits")
    print(f"  Fingerprint: {cert_info.fingerprint_sha256}")
    print(f"  Valid until: {cert_info.not_valid_after}")
    print()
    return True


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate self-signed certificates for OPC UA servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/generate_opcua_certificates.py                         # All OPC UA servers
  python tools/generate_opcua_certificates.py --server scada_server_primary  # Specific server
  python tools/generate_opcua_certificates.py --list                  # List servers
  python tools/generate_opcua_certificates.py --force                 # Overwrite existing
        """,
    )
    parser.add_argument(
        "--server", help="Generate certificate for specific server only"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Generate certificates for all OPC UA servers (default)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all OPC UA servers (no certificate generation)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing certificates",
    )

    args = parser.parse_args()

    # Load configuration
    config = ConfigLoader().load_all()
    opcua_sec = config.get("opcua_security", {})

    # Settings from opcua_security.yml
    key_size = opcua_sec.get("key_size", 2048)
    validity_hours = opcua_sec.get("validity_hours", 8760)
    cert_dir_name = opcua_sec.get("cert_dir", "certs")

    # Discover OPC UA servers
    servers = discover_opcua_servers(config)

    if not servers:
        print("No OPC UA servers found in config/devices.yml")
        return 1

    # List mode
    if args.list:
        print(f"OPC UA Servers ({len(servers)}):")
        print()
        print(f"{'Name':<30} {'Zone':<20} {'Policy':<20} {'Port':<8}")
        print("-" * 80)
        for srv in servers:
            opcua_cfg = srv["opcua_config"]
            policy = opcua_cfg.get("security_policy", "None")
            port = opcua_cfg.get("port", "?")
            print(f"{srv['name']:<30} {srv['zone']:<20} {policy:<20} {port:<8}")

            # Check if certificate exists
            cert_path = Path(cert_dir_name) / f"{srv['name']}.crt"
            if cert_path.exists():
                print(f"  Certificate: {cert_path} (exists)")
            else:
                print("  Certificate: not generated")
        return 0

    # Create certs directory
    certs_dir = Path(cert_dir_name)
    certs_dir.mkdir(exist_ok=True)

    cert_manager = CertificateManager(data_store=None, cert_dir=certs_dir)

    print("OPC UA Certificate Generator")
    print(f"Output directory: {certs_dir.absolute()}")
    print(f"Key size: {key_size} bits")
    print(f"Validity: {validity_hours} hours ({validity_hours / 24:.0f} days)")
    print()

    generated = 0

    if args.server:
        # Generate for specific server
        matching = [s for s in servers if s["name"] == args.server]
        if not matching:
            print(f"Server not found: {args.server}")
            print(f"Available: {', '.join(s['name'] for s in servers)}")
            return 1

        srv = matching[0]
        if await generate_cert_for_server(
            cert_manager,
            certs_dir,
            srv["name"],
            srv["description"],
            key_size,
            validity_hours,
            args.force,
        ):
            generated += 1
    else:
        # Generate for all servers
        for srv in servers:
            if await generate_cert_for_server(
                cert_manager,
                certs_dir,
                srv["name"],
                srv["description"],
                key_size,
                validity_hours,
                args.force,
            ):
                generated += 1

    if generated > 0:
        print(f"Generated {generated} certificate(s)")
        print()
        print("To enable OPC UA encryption:")
        print("  1. Edit config/opcua_security.yml: enforcement_enabled: true")
        print("  2. Restart simulation: python tools/simulator_manager.py")
    else:
        print("No certificates generated (all exist, use --force to overwrite)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

#!/usr/bin/env python3
"""
Generate self-signed certificates for OPC UA servers.

Usage:
    python tools/generate_opcua_certificates.py

Creates certificates in the certs/ directory for OPC UA servers.
"""

import asyncio
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from components.security.encryption import CertificateInfo, CertificateManager


async def generate_opcua_certs():
    """Generate self-signed certificates for OPC UA servers."""

    # Create certs directory
    certs_dir = Path("certs")
    certs_dir.mkdir(exist_ok=True)

    # Initialize certificate manager (DataStore is optional)
    cert_manager = CertificateManager(data_store=None, cert_dir=certs_dir)

    print("Generating OPC UA certificates...")
    print(f"Output directory: {certs_dir.absolute()}\n")

    # Define servers that need certificates
    servers = [
        {
            "name": "scada_backup",
            "common_name": "SCADA Backup Server",
            "organization": "Unseen University Power & Light Co.",
            "validity_days": 365,
        },
        {
            "name": "historian_secure",
            "common_name": "Secure Historian",
            "organization": "Unseen University Power & Light Co.",
            "validity_days": 365,
        },
    ]

    for server in servers:
        print(f"Generating certificate for: {server['common_name']}")

        # Generate self-signed certificate (returns tuple)
        certificate, private_key = cert_manager.generate_self_signed_cert(
            common_name=server["common_name"],
            organization=server["organization"],
            validity_hours=server["validity_days"] * 24,
            key_size=2048,
        )

        # Save certificate and private key
        cert_path = certs_dir / f"{server['name']}.crt"
        key_path = certs_dir / f"{server['name']}.key"

        # Write certificate to file (PEM format)
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        cert_path.write_bytes(cert_pem)

        # Write private key to file (PEM format, no encryption for testing)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_path.write_bytes(key_pem)

        # Get certificate info for display
        cert_info = CertificateInfo.from_x509(certificate)

        print(f"  Certificate: {cert_path}")
        print(f"  Private Key: {key_path}")
        print(f"  Fingerprint: {cert_info.fingerprint_sha256}")
        print(f"  Valid until: {cert_info.not_valid_after}\n")

    print(f"✓ Generated {len(servers)} certificate(s)")
    print("\nYou can now run the simulator with secure OPC UA servers!")
    print("Secure servers will use Basic256Sha256 encryption.")


if __name__ == "__main__":
    asyncio.run(generate_opcua_certs())

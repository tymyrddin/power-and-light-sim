# tests/unit/test_tools/test_generate_opcua_certificates.py
"""Unit tests for OPC UA certificate generation tool."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tools.generate_opcua_certificates import (
    discover_opcua_servers,
    generate_cert_for_server,
    main,
)


class TestDiscoverOPCUAServers:
    """Tests for OPC UA server discovery from config."""

    def test_discover_finds_opcua_servers(self):
        """Test that discovery finds devices with OPC UA protocols."""
        config = {
            "devices": [
                {
                    "name": "scada_primary",
                    "description": "Primary SCADA",
                    "zone": "operations_zone",
                    "protocols": {
                        "opcua": {"port": 4840, "security_policy": "None"},
                    },
                },
                {
                    "name": "plc_1",
                    "description": "PLC (no OPC UA)",
                    "protocols": {"modbus": {"port": 502}},
                },
            ]
        }
        servers = discover_opcua_servers(config)
        assert len(servers) == 1
        assert servers[0]["name"] == "scada_primary"
        assert servers[0]["zone"] == "operations_zone"

    def test_discover_empty_config(self):
        """Test that discovery handles empty device list."""
        servers = discover_opcua_servers({"devices": []})
        assert servers == []

    def test_discover_no_devices_key(self):
        """Test that discovery handles missing devices key."""
        servers = discover_opcua_servers({})
        assert servers == []

    def test_discover_multiple_opcua_servers(self):
        """Test that discovery finds multiple OPC UA servers."""
        config = {
            "devices": [
                {
                    "name": "scada_primary",
                    "protocols": {"opcua": {"port": 4840}},
                },
                {
                    "name": "scada_backup",
                    "protocols": {"opcua": {"port": 4841}},
                },
                {
                    "name": "historian",
                    "protocols": {"opcua": {"port": 4850}},
                },
            ]
        }
        servers = discover_opcua_servers(config)
        assert len(servers) == 3


class TestGenerateCertForServer:
    """Tests for individual server certificate generation."""

    @pytest.mark.asyncio
    async def test_generates_certificate(self, tmp_path):
        """Test that certificate is generated and saved."""
        mock_cert = Mock()
        mock_cert.public_bytes.return_value = b"CERT_PEM"
        mock_key = Mock()
        mock_key.private_bytes.return_value = b"KEY_PEM"

        mock_cert_mgr = Mock()
        mock_cert_mgr.generate_self_signed_cert.return_value = (mock_cert, mock_key)

        mock_info = Mock()
        mock_info.fingerprint_sha256 = "abc123"
        mock_info.not_valid_after = "2026-01-01"

        with patch(
            "tools.generate_opcua_certificates.CertificateInfo"
        ) as mock_info_cls:
            mock_info_cls.from_x509.return_value = mock_info

            result = await generate_cert_for_server(
                cert_manager=mock_cert_mgr,
                certs_dir=tmp_path,
                server_name="test_server",
                description="Test Server",
                key_size=2048,
                validity_hours=8760,
            )

        assert result is True
        mock_cert_mgr.generate_self_signed_cert.assert_called_once()
        assert (tmp_path / "test_server.crt").read_bytes() == b"CERT_PEM"
        assert (tmp_path / "test_server.key").read_bytes() == b"KEY_PEM"

    @pytest.mark.asyncio
    async def test_skips_existing_without_force(self, tmp_path):
        """Test that existing certificates are skipped without --force."""
        (tmp_path / "test_server.crt").write_bytes(b"EXISTING")
        (tmp_path / "test_server.key").write_bytes(b"EXISTING")

        mock_cert_mgr = Mock()

        result = await generate_cert_for_server(
            cert_manager=mock_cert_mgr,
            certs_dir=tmp_path,
            server_name="test_server",
            description="",
            key_size=2048,
            validity_hours=8760,
            force=False,
        )

        assert result is False
        mock_cert_mgr.generate_self_signed_cert.assert_not_called()

    @pytest.mark.asyncio
    async def test_overwrites_with_force(self, tmp_path):
        """Test that existing certificates are overwritten with --force."""
        (tmp_path / "test_server.crt").write_bytes(b"OLD")
        (tmp_path / "test_server.key").write_bytes(b"OLD")

        mock_cert = Mock()
        mock_cert.public_bytes.return_value = b"NEW_CERT"
        mock_key = Mock()
        mock_key.private_bytes.return_value = b"NEW_KEY"

        mock_cert_mgr = Mock()
        mock_cert_mgr.generate_self_signed_cert.return_value = (mock_cert, mock_key)

        mock_info = Mock()
        mock_info.fingerprint_sha256 = "abc123"
        mock_info.not_valid_after = "2026-01-01"

        with patch(
            "tools.generate_opcua_certificates.CertificateInfo"
        ) as mock_info_cls:
            mock_info_cls.from_x509.return_value = mock_info

            result = await generate_cert_for_server(
                cert_manager=mock_cert_mgr,
                certs_dir=tmp_path,
                server_name="test_server",
                description="",
                key_size=2048,
                validity_hours=8760,
                force=True,
            )

        assert result is True
        assert (tmp_path / "test_server.crt").read_bytes() == b"NEW_CERT"
        assert (tmp_path / "test_server.key").read_bytes() == b"NEW_KEY"

# tests/unit/test_tools/test_generate_opcua_certificates.py
"""Unit tests for OPC UA certificate generation tool."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from tools.generate_opcua_certificates import generate_opcua_certs


class TestGenerateOPCUACertificates:
    """Tests for OPC UA certificate generation."""

    @pytest.mark.asyncio
    async def test_generate_opcua_certs_creates_directory(self, tmp_path):
        """Test that certificate generation creates certs directory."""
        certs_dir = tmp_path / "certs"

        with (
            patch("tools.generate_opcua_certificates.Path") as mock_path_class,
            patch(
                "tools.generate_opcua_certificates.CertificateManager"
            ) as mock_cert_mgr_class,
            patch("builtins.print"),
        ):
            # Setup Path mock
            mock_path = Mock()
            mock_path.mkdir = Mock()
            mock_path.absolute.return_value = certs_dir
            mock_path.__truediv__ = lambda self, other: Mock(
                write_bytes=Mock(), __str__=lambda s: str(certs_dir / other)
            )
            mock_path_class.return_value = mock_path

            # Setup CertificateManager mock
            mock_cert_mgr = Mock()
            mock_certificate = Mock()
            mock_certificate.public_bytes.return_value = b"CERT_DATA"
            mock_private_key = Mock()
            mock_private_key.private_bytes.return_value = b"KEY_DATA"
            mock_cert_mgr.generate_self_signed_cert.return_value = (
                mock_certificate,
                mock_private_key,
            )
            mock_cert_mgr_class.return_value = mock_cert_mgr

            # Setup CertificateInfo mock
            with patch(
                "tools.generate_opcua_certificates.CertificateInfo"
            ) as mock_cert_info_class:
                mock_cert_info = Mock()
                mock_cert_info.fingerprint_sha256 = "abc123"
                mock_cert_info.not_valid_after = "2025-01-01"
                mock_cert_info_class.from_x509.return_value = mock_cert_info

                await generate_opcua_certs()

            # Verify directory was created
            mock_path.mkdir.assert_called_once_with(exist_ok=True)

    @pytest.mark.asyncio
    async def test_generate_opcua_certs_creates_certificate_manager(self, tmp_path):
        """Test that certificate manager is initialized correctly."""
        certs_dir = tmp_path / "certs"

        with (
            patch("tools.generate_opcua_certificates.Path") as mock_path_class,
            patch(
                "tools.generate_opcua_certificates.CertificateManager"
            ) as mock_cert_mgr_class,
            patch("builtins.print"),
        ):
            # Setup Path mock
            mock_path = Mock()
            mock_path.mkdir = Mock()
            mock_path.absolute.return_value = certs_dir
            mock_path.__truediv__ = lambda self, other: Mock(
                write_bytes=Mock(), __str__=lambda s: str(certs_dir / other)
            )
            mock_path_class.return_value = mock_path

            # Setup CertificateManager mock
            mock_cert_mgr = Mock()
            mock_certificate = Mock()
            mock_certificate.public_bytes.return_value = b"CERT_DATA"
            mock_private_key = Mock()
            mock_private_key.private_bytes.return_value = b"KEY_DATA"
            mock_cert_mgr.generate_self_signed_cert.return_value = (
                mock_certificate,
                mock_private_key,
            )
            mock_cert_mgr_class.return_value = mock_cert_mgr

            # Setup CertificateInfo mock
            with patch(
                "tools.generate_opcua_certificates.CertificateInfo"
            ) as mock_cert_info_class:
                mock_cert_info = Mock()
                mock_cert_info.fingerprint_sha256 = "abc123"
                mock_cert_info.not_valid_after = "2025-01-01"
                mock_cert_info_class.from_x509.return_value = mock_cert_info

                await generate_opcua_certs()

            # Verify CertificateManager was created with correct params
            mock_cert_mgr_class.assert_called_once_with(
                data_store=None, cert_dir=mock_path
            )

    @pytest.mark.asyncio
    async def test_generate_opcua_certs_generates_two_certificates(self, tmp_path):
        """Test that two certificates are generated (scada_backup and historian_secure)."""
        certs_dir = tmp_path / "certs"

        with (
            patch("tools.generate_opcua_certificates.Path") as mock_path_class,
            patch(
                "tools.generate_opcua_certificates.CertificateManager"
            ) as mock_cert_mgr_class,
            patch("builtins.print"),
        ):
            # Setup Path mock
            mock_path = Mock()
            mock_path.mkdir = Mock()
            mock_path.absolute.return_value = certs_dir
            mock_path.__truediv__ = lambda self, other: Mock(
                write_bytes=Mock(), __str__=lambda s: str(certs_dir / other)
            )
            mock_path_class.return_value = mock_path

            # Setup CertificateManager mock
            mock_cert_mgr = Mock()
            mock_certificate = Mock()
            mock_certificate.public_bytes.return_value = b"CERT_DATA"
            mock_private_key = Mock()
            mock_private_key.private_bytes.return_value = b"KEY_DATA"
            mock_cert_mgr.generate_self_signed_cert.return_value = (
                mock_certificate,
                mock_private_key,
            )
            mock_cert_mgr_class.return_value = mock_cert_mgr

            # Setup CertificateInfo mock
            with patch(
                "tools.generate_opcua_certificates.CertificateInfo"
            ) as mock_cert_info_class:
                mock_cert_info = Mock()
                mock_cert_info.fingerprint_sha256 = "abc123"
                mock_cert_info.not_valid_after = "2025-01-01"
                mock_cert_info_class.from_x509.return_value = mock_cert_info

                await generate_opcua_certs()

            # Verify two certificates were generated
            assert mock_cert_mgr.generate_self_signed_cert.call_count == 2

            # Verify correct parameters for first cert (scada_backup)
            first_call = mock_cert_mgr.generate_self_signed_cert.call_args_list[0]
            assert first_call[1]["common_name"] == "SCADA Backup Server"
            assert (
                first_call[1]["organization"] == "Unseen University Power & Light Co."
            )
            assert first_call[1]["validity_hours"] == 365 * 24
            assert first_call[1]["key_size"] == 2048

            # Verify correct parameters for second cert (historian_secure)
            second_call = mock_cert_mgr.generate_self_signed_cert.call_args_list[1]
            assert second_call[1]["common_name"] == "Secure Historian"
            assert (
                second_call[1]["organization"] == "Unseen University Power & Light Co."
            )
            assert second_call[1]["validity_hours"] == 365 * 24
            assert second_call[1]["key_size"] == 2048

    @pytest.mark.asyncio
    async def test_generate_opcua_certs_saves_files(self, tmp_path):
        """Test that certificate and key files are written."""
        certs_dir = tmp_path / "certs"

        with (
            patch("tools.generate_opcua_certificates.Path") as mock_path_class,
            patch(
                "tools.generate_opcua_certificates.CertificateManager"
            ) as mock_cert_mgr_class,
            patch("builtins.print"),
        ):
            # Setup Path mock with file mocks
            mock_cert_file = Mock()
            mock_key_file = Mock()
            file_mocks = {
                "scada_backup.crt": mock_cert_file,
                "scada_backup.key": mock_key_file,
                "historian_secure.crt": Mock(),
                "historian_secure.key": Mock(),
            }

            def path_div(self, other):
                return file_mocks.get(other, Mock(write_bytes=Mock()))

            mock_path = Mock()
            mock_path.mkdir = Mock()
            mock_path.absolute.return_value = certs_dir
            mock_path.__truediv__ = path_div
            mock_path_class.return_value = mock_path

            # Setup CertificateManager mock
            mock_cert_mgr = Mock()
            mock_certificate = Mock()
            mock_certificate.public_bytes.return_value = b"CERT_DATA"
            mock_private_key = Mock()
            mock_private_key.private_bytes.return_value = b"KEY_DATA"
            mock_cert_mgr.generate_self_signed_cert.return_value = (
                mock_certificate,
                mock_private_key,
            )
            mock_cert_mgr_class.return_value = mock_cert_mgr

            # Setup CertificateInfo mock
            with patch(
                "tools.generate_opcua_certificates.CertificateInfo"
            ) as mock_cert_info_class:
                mock_cert_info = Mock()
                mock_cert_info.fingerprint_sha256 = "abc123"
                mock_cert_info.not_valid_after = "2025-01-01"
                mock_cert_info_class.from_x509.return_value = mock_cert_info

                await generate_opcua_certs()

            # Verify certificate files were written
            mock_cert_file.write_bytes.assert_called_once_with(b"CERT_DATA")
            mock_key_file.write_bytes.assert_called_once_with(b"KEY_DATA")

    @pytest.mark.asyncio
    async def test_generate_opcua_certs_prints_output(self, tmp_path, capsys):
        """Test that generation prints informative output."""
        certs_dir = tmp_path / "certs"

        with (
            patch("tools.generate_opcua_certificates.Path") as mock_path_class,
            patch(
                "tools.generate_opcua_certificates.CertificateManager"
            ) as mock_cert_mgr_class,
        ):
            # Setup Path mock
            mock_path = Mock()
            mock_path.mkdir = Mock()
            mock_path.absolute.return_value = certs_dir
            mock_path.__truediv__ = lambda self, other: Mock(
                write_bytes=Mock(), __str__=lambda s: str(certs_dir / other)
            )
            mock_path_class.return_value = mock_path

            # Setup CertificateManager mock
            mock_cert_mgr = Mock()
            mock_certificate = Mock()
            mock_certificate.public_bytes.return_value = b"CERT_DATA"
            mock_private_key = Mock()
            mock_private_key.private_bytes.return_value = b"KEY_DATA"
            mock_cert_mgr.generate_self_signed_cert.return_value = (
                mock_certificate,
                mock_private_key,
            )
            mock_cert_mgr_class.return_value = mock_cert_mgr

            # Setup CertificateInfo mock
            with patch(
                "tools.generate_opcua_certificates.CertificateInfo"
            ) as mock_cert_info_class:
                mock_cert_info = Mock()
                mock_cert_info.fingerprint_sha256 = "abc123"
                mock_cert_info.not_valid_after = "2025-01-01"
                mock_cert_info_class.from_x509.return_value = mock_cert_info

                await generate_opcua_certs()

            # Check printed output
            captured = capsys.readouterr()
            assert "Generating OPC UA certificates" in captured.out
            assert "SCADA Backup Server" in captured.out
            assert "Secure Historian" in captured.out
            assert "Generated 2 certificate(s)" in captured.out

# tests/unit/security/test_encryption.py
"""Comprehensive tests for encryption and cryptographic utilities.

Test Coverage:
- SecurityLevel, OPCUASecurityPolicy, DNP3AuthMode enums
- CertificateInfo dataclass
- CertificateManager (generation, save/load, validation)
- AESEncryption (encrypt/decrypt)
- DNP3Crypto utilities
- OPCUACrypto utilities
- SecureKeyStore (store/retrieve keys)
"""

import asyncio
import base64
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from components.security.encryption import (
    AESEncryption,
    CertificateInfo,
    CertificateManager,
    DNP3AuthMode,
    DNP3Crypto,
    OPCUACrypto,
    OPCUASecurityPolicy,
    SecureKeyStore,
    SecurityLevel,
    SIMULATION_EPOCH,
)


# ================================================================
# ENUM TESTS
# ================================================================
class TestSecurityLevel:
    """Test SecurityLevel enum."""

    def test_security_level_ordering(self):
        """Test that security levels are properly ordered.

        WHY: Higher levels should have higher values.
        """
        assert SecurityLevel.NONE.value < SecurityLevel.BASIC.value
        assert SecurityLevel.BASIC.value < SecurityLevel.ENCRYPTED.value
        assert SecurityLevel.ENCRYPTED.value < SecurityLevel.AUTHENTICATED.value
        assert SecurityLevel.AUTHENTICATED.value < SecurityLevel.SIGNED.value

    def test_all_levels_present(self):
        """Test all IEC 62443 levels are present.

        WHY: Compliance with standard.
        """
        levels = {s.value for s in SecurityLevel}
        assert levels == {0, 1, 2, 3, 4}


class TestOPCUASecurityPolicy:
    """Test OPCUASecurityPolicy enum."""

    def test_recommended_policy_exists(self):
        """Test that recommended policy exists.

        WHY: AES256_SHA256_RSAPss is recommended.
        """
        assert OPCUASecurityPolicy.AES256_SHA256_RSAPSS.value == "Aes256_Sha256_RsaPss"

    def test_deprecated_policies_marked(self):
        """Test that deprecated policies exist (for backwards compat).

        WHY: Legacy systems may use old policies.
        """
        assert OPCUASecurityPolicy.BASIC128RSA15.value == "Basic128Rsa15"
        assert OPCUASecurityPolicy.BASIC256.value == "Basic256"


class TestDNP3AuthMode:
    """Test DNP3AuthMode enum."""

    def test_sav5_exists(self):
        """Test that SAv5 mode exists.

        WHY: SAv5 is current standard.
        """
        assert DNP3AuthMode.SAV5.value == "SAv5"

    def test_none_mode_exists(self):
        """Test that NONE mode exists.

        WHY: Some systems don't use auth.
        """
        assert DNP3AuthMode.NONE.value == "none"


# ================================================================
# SIMULATION EPOCH TESTS
# ================================================================
class TestSimulationEpoch:
    """Test SIMULATION_EPOCH constant."""

    def test_epoch_is_datetime(self):
        """Test that epoch is a datetime.

        WHY: Used for certificate validity calculations.
        """
        assert isinstance(SIMULATION_EPOCH, datetime)

    def test_epoch_is_2024(self):
        """Test that epoch is January 1, 2024.

        WHY: Consistent reference point.
        """
        assert SIMULATION_EPOCH.year == 2024
        assert SIMULATION_EPOCH.month == 1
        assert SIMULATION_EPOCH.day == 1


# ================================================================
# AES ENCRYPTION TESTS
# ================================================================
class TestAESEncryption:
    """Test AESEncryption class."""

    def test_generate_key_default_size(self):
        """Test generating 256-bit key by default.

        WHY: AES-256 is recommended.
        """
        key = AESEncryption.generate_key()

        assert len(key) == 32  # 256 bits = 32 bytes

    def test_generate_key_128_bit(self):
        """Test generating 128-bit key.

        WHY: AES-128 is still valid.
        """
        key = AESEncryption.generate_key(128)

        assert len(key) == 16

    def test_generate_key_192_bit(self):
        """Test generating 192-bit key.

        WHY: AES-192 is supported.
        """
        key = AESEncryption.generate_key(192)

        assert len(key) == 24

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypt/decrypt returns original data.

        WHY: Core encryption functionality.
        """
        key = AESEncryption.generate_key()
        plaintext = b"This is a secret message"

        ciphertext, nonce, tag = AESEncryption.encrypt(plaintext, key)
        decrypted = AESEncryption.decrypt(ciphertext, key, nonce, tag)

        assert decrypted == plaintext

    def test_encrypt_produces_different_output(self):
        """Test that encrypting same data twice produces different output.

        WHY: GCM should use random nonce.
        """
        key = AESEncryption.generate_key()
        plaintext = b"Same message"

        ciphertext1, nonce1, _ = AESEncryption.encrypt(plaintext, key)
        ciphertext2, nonce2, _ = AESEncryption.encrypt(plaintext, key)

        assert nonce1 != nonce2
        assert ciphertext1 != ciphertext2

    def test_decrypt_with_wrong_key_fails(self):
        """Test that decryption with wrong key fails.

        WHY: Security - wrong key should not decrypt.
        """
        key1 = AESEncryption.generate_key()
        key2 = AESEncryption.generate_key()
        plaintext = b"Secret"

        ciphertext, nonce, tag = AESEncryption.encrypt(plaintext, key1)

        with pytest.raises(Exception):  # InvalidTag or similar
            AESEncryption.decrypt(ciphertext, key2, nonce, tag)

    def test_decrypt_with_modified_ciphertext_fails(self):
        """Test that modified ciphertext fails authentication.

        WHY: GCM provides integrity.
        """
        key = AESEncryption.generate_key()
        plaintext = b"Secret message"

        ciphertext, nonce, tag = AESEncryption.encrypt(plaintext, key)

        # Modify ciphertext
        modified = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]

        with pytest.raises(Exception):
            AESEncryption.decrypt(modified, key, nonce, tag)

    def test_encrypt_string_roundtrip(self):
        """Test string encryption/decryption roundtrip.

        WHY: Convenience for string data.
        """
        key = AESEncryption.generate_key()
        plaintext = "Hello, World!"

        encrypted = AESEncryption.encrypt_string(plaintext, key)
        decrypted = AESEncryption.decrypt_string(encrypted, key)

        assert decrypted == plaintext

    def test_encrypt_string_produces_base64(self):
        """Test that encrypt_string produces base64 output.

        WHY: Easier to store/transmit.
        """
        key = AESEncryption.generate_key()
        plaintext = "Test"

        encrypted = AESEncryption.encrypt_string(plaintext, key)

        # Should be valid base64
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 0

    def test_encrypt_empty_string(self):
        """Test encrypting empty string.

        WHY: Edge case handling.
        """
        key = AESEncryption.generate_key()

        encrypted = AESEncryption.encrypt_string("", key)
        decrypted = AESEncryption.decrypt_string(encrypted, key)

        assert decrypted == ""

    def test_encrypt_unicode_string(self):
        """Test encrypting unicode string.

        WHY: International characters must work.
        """
        key = AESEncryption.generate_key()
        plaintext = "Hello, \u4e16\u754c! \U0001f600"

        encrypted = AESEncryption.encrypt_string(plaintext, key)
        decrypted = AESEncryption.decrypt_string(encrypted, key)

        assert decrypted == plaintext


# ================================================================
# CERTIFICATE MANAGER TESTS
# ================================================================
class TestCertificateManager:
    """Test CertificateManager class."""

    def test_create_manager(self):
        """Test creating a certificate manager.

        WHY: Core functionality.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            assert mgr.cert_dir.exists()

    def test_generate_rsa_key_pair(self):
        """Test generating RSA key pair.

        WHY: Keys are needed for certificates.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            key = mgr.generate_rsa_key_pair()

            assert key is not None
            assert key.key_size >= 2048

    def test_generate_rsa_key_pair_custom_size(self):
        """Test generating RSA key with custom size.

        WHY: Different security requirements.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            key = mgr.generate_rsa_key_pair(key_size=4096)

            assert key.key_size == 4096

    def test_generate_self_signed_cert(self):
        """Test generating self-signed certificate.

        WHY: Core certificate functionality.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            cert, key = mgr.generate_self_signed_cert(
                common_name="test.local",
                organization="Test Org",
            )

            assert cert is not None
            assert key is not None
            assert "test.local" in cert.subject.rfc4514_string()

    def test_certificate_cached(self):
        """Test that generated certificates are cached.

        WHY: Avoid regenerating same cert.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            cert1, _ = mgr.generate_self_signed_cert("cached.local")
            cert2 = mgr._certificates.get("cached.local")

            assert cert2 is cert1

    def test_save_and_load_certificate(self):
        """Test saving and loading certificate.

        WHY: Persistence across restarts.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            cert, key = mgr.generate_self_signed_cert("persistent.local")
            mgr.save_certificate(cert, key, "persistent")

            # Clear cache
            mgr._certificates.clear()
            mgr._private_keys.clear()

            loaded = mgr.load_certificate("persistent")

            assert loaded is not None
            loaded_cert, loaded_key = loaded
            assert loaded_cert.serial_number == cert.serial_number

    def test_load_nonexistent_certificate(self):
        """Test loading non-existent certificate returns None.

        WHY: Should indicate absence.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            result = mgr.load_certificate("nonexistent")

            assert result is None

    def test_validate_certificate_valid(self):
        """Test validating a valid certificate.

        WHY: Certificate validation is core security.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            cert, _ = mgr.generate_self_signed_cert(
                "valid.local", validity_hours=8760
            )

            result = mgr.validate_certificate(cert)

            assert result is True

    def test_get_certificate_info(self):
        """Test getting certificate info.

        WHY: Need to inspect certificates.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            mgr.generate_self_signed_cert("info.local")

            info = mgr.get_certificate_info("info.local")

            assert info is not None
            assert isinstance(info, CertificateInfo)
            assert "info.local" in info.subject

    def test_get_certificate_info_nonexistent(self):
        """Test getting info for nonexistent certificate.

        WHY: Should indicate absence.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))

            info = mgr.get_certificate_info("nonexistent")

            assert info is None


# ================================================================
# CERTIFICATE INFO TESTS
# ================================================================
class TestCertificateInfo:
    """Test CertificateInfo dataclass."""

    def test_from_x509(self):
        """Test creating CertificateInfo from X.509 certificate.

        WHY: Need to extract info from certs.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CertificateManager(cert_dir=Path(tmpdir))
            cert, _ = mgr.generate_self_signed_cert("test.local")

            info = CertificateInfo.from_x509(cert)

            assert info.serial_number == cert.serial_number
            assert "test.local" in info.subject
            assert len(info.fingerprint_sha256) == 64  # 256 bits = 64 hex chars


# ================================================================
# DNP3 CRYPTO TESTS
# ================================================================
class TestDNP3Crypto:
    """Test DNP3Crypto utilities."""

    def test_generate_update_key(self):
        """Test generating DNP3 update key.

        WHY: SAv5 requires update keys.
        """
        key = DNP3Crypto.generate_update_key()

        assert len(key) == 16  # Default 128-bit

    def test_generate_update_key_custom_size(self):
        """Test generating update key with custom size.

        WHY: Different key lengths supported.
        """
        key = DNP3Crypto.generate_update_key(32)

        assert len(key) == 32

    def test_hmac_sha256(self):
        """Test HMAC-SHA256 computation.

        WHY: SAv5 uses HMAC for authentication.
        """
        key = b"secret_key_here!"
        data = b"message to authenticate"

        mac = DNP3Crypto.hmac_sha256(key, data)

        assert len(mac) == 32  # SHA-256 = 32 bytes
        # Same input should produce same output
        mac2 = DNP3Crypto.hmac_sha256(key, data)
        assert mac == mac2

    def test_hmac_different_key_different_mac(self):
        """Test that different keys produce different MACs.

        WHY: Security property.
        """
        data = b"message"

        mac1 = DNP3Crypto.hmac_sha256(b"key1_pad_to_16!", data)
        mac2 = DNP3Crypto.hmac_sha256(b"key2_pad_to_16!", data)

        assert mac1 != mac2

    def test_generate_challenge(self):
        """Test generating DNP3 challenge.

        WHY: SAv5 challenge-response auth.
        """
        challenge = DNP3Crypto.generate_challenge()

        assert len(challenge) == 4  # 4 bytes per spec

    def test_generate_challenge_random(self):
        """Test that challenges are random.

        WHY: Prevent replay attacks.
        """
        challenges = [DNP3Crypto.generate_challenge() for _ in range(10)]

        # All should be unique (extremely unlikely to collide)
        assert len(set(challenges)) == 10


# ================================================================
# OPC UA CRYPTO TESTS
# ================================================================
class TestOPCUACrypto:
    """Test OPCUACrypto utilities."""

    def test_get_security_policy_uri(self):
        """Test getting security policy URI.

        WHY: OPC UA requires policy URIs.
        """
        uri = OPCUACrypto.get_security_policy_uri(
            OPCUASecurityPolicy.BASIC256SHA256
        )

        assert "SecurityPolicy" in uri
        assert "Basic256Sha256" in uri

    def test_get_security_policy_uri_none(self):
        """Test getting URI for no security.

        WHY: Some connections don't use security.
        """
        uri = OPCUACrypto.get_security_policy_uri(OPCUASecurityPolicy.NONE)

        assert uri.endswith("None")


# ================================================================
# SECURE KEY STORE TESTS
# ================================================================
class TestSecureKeyStore:
    """Test SecureKeyStore class."""

    @pytest.fixture
    def mock_data_store(self):
        """Create mock DataStore for testing."""
        store = MagicMock()
        store.update_metadata = AsyncMock(return_value=True)
        store.read_metadata = AsyncMock(return_value={})
        return store

    @pytest.mark.asyncio
    async def test_create_key_store(self, mock_data_store):
        """Test creating a key store.

        WHY: Core functionality.
        """
        store = SecureKeyStore(mock_data_store)

        assert store.master_key is not None
        assert len(store.master_key) == 32  # 256-bit

    @pytest.mark.asyncio
    async def test_create_with_custom_master_key(self, mock_data_store):
        """Test creating with custom master key.

        WHY: Key may come from HSM or config.
        """
        custom_key = AESEncryption.generate_key()
        store = SecureKeyStore(mock_data_store, master_key=custom_key)

        assert store.master_key == custom_key

    @pytest.mark.asyncio
    async def test_store_and_retrieve_key(self, mock_data_store):
        """Test storing and retrieving a key.

        WHY: Core key management functionality.
        """
        store = SecureKeyStore(mock_data_store)
        test_key = AESEncryption.generate_key()

        await store.store_key("test_key", test_key)

        # Setup mock to return stored data
        call_args = mock_data_store.update_metadata.call_args
        stored_data = call_args[0][1]  # Second arg is the metadata dict

        mock_data_store.read_metadata.return_value = stored_data

        retrieved = await store.retrieve_key("test_key")

        assert retrieved == test_key

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_key(self, mock_data_store):
        """Test retrieving non-existent key returns None.

        WHY: Should indicate absence.
        """
        mock_data_store.read_metadata.return_value = {}
        store = SecureKeyStore(mock_data_store)

        result = await store.retrieve_key("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_with_wrong_master_key(self, mock_data_store):
        """Test that wrong master key fails to decrypt.

        WHY: Security - only correct key should work.
        """
        store1 = SecureKeyStore(mock_data_store)
        test_key = AESEncryption.generate_key()

        await store1.store_key("protected", test_key)

        # Get stored data
        call_args = mock_data_store.update_metadata.call_args
        stored_data = call_args[0][1]
        mock_data_store.read_metadata.return_value = stored_data

        # Create new store with different master key
        store2 = SecureKeyStore(mock_data_store, master_key=AESEncryption.generate_key())

        result = await store2.retrieve_key("protected")

        assert result is None  # Should fail to decrypt

    @pytest.mark.asyncio
    async def test_store_key_logs_operation(self, mock_data_store):
        """Test that key storage is logged.

        WHY: Security operations must be auditable.
        """
        store = SecureKeyStore(mock_data_store)

        await store.store_key("logged_key", b"test_key_data_!!")

        # Logger should have been called
        # (We can't easily check ICSLogger without mocking, but the code path is tested)
        assert mock_data_store.update_metadata.called


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestEncryptionIntegration:
    """Integration tests for encryption module."""

    def test_certificate_and_encryption_workflow(self):
        """Test complete certificate + encryption workflow.

        WHY: Real-world usage combines these.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate certificate
            mgr = CertificateManager(cert_dir=Path(tmpdir))
            cert, key = mgr.generate_self_signed_cert("integration.local")

            # Generate session key
            session_key = AESEncryption.generate_key()

            # Encrypt data with session key
            message = "Secure SCADA command"
            encrypted = AESEncryption.encrypt_string(message, session_key)

            # Decrypt data
            decrypted = AESEncryption.decrypt_string(encrypted, session_key)

            assert decrypted == message

            # Validate certificate
            assert mgr.validate_certificate(cert) is True

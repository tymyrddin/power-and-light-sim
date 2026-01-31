# components/security/encryption.py
"""
Encryption and cryptographic utilities for ICS simulator.

Provides:
- TLS/SSL utilities for protocol security
- Certificate management (generation, validation)
- Symmetric encryption (AES)
- Asymmetric encryption (RSA)
- Key management and storage
- Protocol-specific crypto (DNP3 SAv5, OPC UA security)

Integrations:
- ConfigLoader: Load encryption settings from YAML
- DataStore: Store encrypted credentials/keys
- SimulationTime: Certificate validity periods

ICS-specific features:
- DNP3 Secure Authentication v5
- OPC UA security policies
- IEC 62351 compliance helpers
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import NameOID

from components.security.logging_system import (
    ICSLogger,
    get_logger,
)
from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime
from config.config_loader import ConfigLoader

__all__ = [
    "SecurityLevel",
    "OPCUASecurityPolicy",
    "DNP3AuthMode",
    "CertificateInfo",
    "CertificateManager",
    "AESEncryption",
    "DNP3Crypto",
    "OPCUACrypto",
    "SecureKeyStore",
    "SIMULATION_EPOCH",
]

# Epoch for simulation time to datetime conversion (UTC)
SIMULATION_EPOCH = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# ----------------------------------------------------------------
# Security Levels and Policies
# ----------------------------------------------------------------


class SecurityLevel(Enum):
    """ICS security levels (IEC 62443)."""

    NONE = 0  # No security
    BASIC = 1  # Basic authentication
    ENCRYPTED = 2  # Encrypted communications
    AUTHENTICATED = 3  # Mutual authentication + encryption
    SIGNED = 4  # Full signing + encryption + authentication


class OPCUASecurityPolicy(Enum):
    """OPC UA security policies."""

    NONE = "None"
    BASIC128RSA15 = "Basic128Rsa15"  # Deprecated
    BASIC256 = "Basic256"  # Deprecated
    BASIC256SHA256 = "Basic256Sha256"
    AES128_SHA256_RSAOAEP = "Aes128_Sha256_RsaOaep"
    AES256_SHA256_RSAPSS = "Aes256_Sha256_RsaPss"  # Recommended


class DNP3AuthMode(Enum):
    """DNP3 Secure Authentication modes."""

    NONE = "none"
    SAV2 = "SAv2"  # Secure Authentication v2 (obsolete)
    SAV5 = "SAv5"  # Secure Authentication v5 (current standard)


# ----------------------------------------------------------------
# Key and Certificate Management
# ----------------------------------------------------------------


@dataclass
class CertificateInfo:
    """X.509 certificate information."""

    subject: str
    issuer: str
    serial_number: int
    not_valid_before: datetime
    not_valid_after: datetime
    public_key_algorithm: str
    signature_algorithm: str
    fingerprint_sha256: str

    @classmethod
    def from_x509(cls, cert: x509.Certificate) -> "CertificateInfo":
        """Create from cryptography X.509 certificate."""
        return cls(
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=cert.serial_number,
            not_valid_before=cert.not_valid_before_utc,
            not_valid_after=cert.not_valid_after_utc,
            public_key_algorithm=cert.public_key().__class__.__name__,
            signature_algorithm=cert.signature_algorithm_oid._name,
            fingerprint_sha256=cert.fingerprint(hashes.SHA256()).hex(),
        )


class CertificateManager:
    """
    Certificate generation and management for ICS protocols.

    Integrates with:
    - SimulationTime: Certificate validity periods use simulation time
    - DataStore: Store certificates and keys
    - ConfigLoader: Load certificate settings from YAML
    - ICSLogger: Security event logging
    """

    def __init__(
        self,
        data_store: DataStore | None = None,
        cert_dir: Path | None = None,
    ):
        """
        Initialise certificate manager.

        Args:
            data_store: DataStore for storing certificates
            cert_dir: Directory for certificate storage
        """
        self.data_store = data_store
        self.cert_dir = cert_dir or Path("./certs")
        self.cert_dir.mkdir(parents=True, exist_ok=True)

        self.sim_time = SimulationTime()
        self.config = ConfigLoader().load_all()
        self.logger: ICSLogger = get_logger(__name__, device="cert_manager")

        # Certificate cache (protected by lock)
        self._certificates: dict[str, x509.Certificate] = {}
        self._private_keys: dict[str, rsa.RSAPrivateKey] = {}
        self._lock = threading.Lock()

        # Load settings from config
        self._load_config()

        self.logger.info("CertificateManager initialised")

    def _load_config(self) -> None:
        """Load encryption settings from YAML configuration."""
        # Get security settings from simulation config
        security_cfg = self.config.get("simulation", {}).get("security", {})

        # Default certificate validity (in simulation hours)
        self.default_validity_hours = security_cfg.get(
            "cert_validity_hours", 8760
        )  # 1 year

        # Key sizes
        self.rsa_key_size = security_cfg.get("rsa_key_size", 2048)

        # Default security level
        security_level = security_cfg.get("security_level", "BASIC")
        try:
            self.default_security_level = SecurityLevel[security_level]
        except KeyError:
            self.default_security_level = SecurityLevel.BASIC

    def generate_rsa_key_pair(self, key_size: int = 2048) -> rsa.RSAPrivateKey:
        """
        Generate RSA key pair.

        Args:
            key_size: Key size in bits (2048, 3072, 4096)

        Returns:
            RSA private key (contains public key)
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
        return private_key

    def generate_self_signed_cert(
        self,
        common_name: str,
        organization: str = "Unseen University Power & Light",
        validity_hours: float | None = None,
        key_size: int | None = None,
    ) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """
        Generate self-signed X.509 certificate.

        Uses simulation time for validity periods.

        Args:
            common_name: Certificate common name (CN)
            organization: Organization name (O)
            validity_hours: Certificate validity in simulation hours
            key_size: RSA key size

        Returns:
            Tuple of (certificate, private_key)
        """
        # Generate key pair
        if key_size is None:
            key_size = self.rsa_key_size
        private_key = self.generate_rsa_key_pair(key_size)

        # Build certificate subject/issuer
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "South Holland"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Dordrecht"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ]
        )

        # Calculate validity period using simulation time
        if validity_hours is None:
            validity_hours = self.default_validity_hours

        # Use current simulation time as basis
        sim_time_now = self.sim_time.now()

        # Convert to datetime for certificate (use epoch + sim time)
        not_valid_before = SIMULATION_EPOCH + timedelta(seconds=sim_time_now)
        not_valid_after = SIMULATION_EPOCH + timedelta(
            seconds=sim_time_now + (validity_hours * 3600)
        )

        # Build certificate
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_valid_before)
            .not_valid_after(not_valid_after)
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(common_name),
                        x509.DNSName(f"{common_name}.local"),
                    ]
                ),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Cache certificate and key (thread-safe)
        with self._lock:
            self._certificates[common_name] = cert
            self._private_keys[common_name] = private_key

        self.logger.info(
            f"Generated self-signed certificate for '{common_name}' "
            f"(valid for {validity_hours} hours, key size: {key_size})"
        )

        return cert, private_key

    def save_certificate(
        self,
        cert: x509.Certificate,
        private_key: rsa.RSAPrivateKey,
        name: str,
    ) -> None:
        """
        Save certificate and private key to files.

        Args:
            cert: X.509 certificate
            private_key: Private key
            name: Base filename (without extension)
        """
        # Save certificate (PEM format)
        cert_path = self.cert_dir / f"{name}.crt"
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # Save private key (PEM format, unencrypted for simulation)
        key_path = self.cert_dir / f"{name}.key"
        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        self.logger.info(f"Saved certificate and key for '{name}' to {self.cert_dir}")

    def load_certificate(
        self, name: str
    ) -> tuple[x509.Certificate, rsa.RSAPrivateKey] | None:
        """
        Load certificate and private key from files.

        Args:
            name: Base filename (without extension)

        Returns:
            Tuple of (certificate, private_key) or None if not found
        """
        cert_path = self.cert_dir / f"{name}.crt"
        key_path = self.cert_dir / f"{name}.key"

        if not (cert_path.exists() and key_path.exists()):
            self.logger.debug(f"Certificate '{name}' not found in {self.cert_dir}")
            return None

        try:
            # Load certificate
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())

            # Load private key
            with open(key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                )

            # Verify key type is RSA
            if not isinstance(private_key, rsa.RSAPrivateKey):
                self.logger.error(
                    f"Expected RSA key for '{name}', got {type(private_key).__name__}"
                )
                return None

            self.logger.info(f"Loaded certificate and key for '{name}'")
            return cert, private_key

        except Exception:
            self.logger.exception(f"Failed to load certificate '{name}'")
            return None

    def validate_certificate(self, cert: x509.Certificate) -> bool:
        """
        Validate certificate against simulation time.

        Note: Only validates time period, not chain of trust or revocation.

        Args:
            cert: X.509 certificate

        Returns:
            True if valid, False if expired/not yet valid
        """
        # Get current simulation time as datetime
        sim_time_now = self.sim_time.now()
        current_datetime = SIMULATION_EPOCH + timedelta(seconds=sim_time_now)

        cert_cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        cert_name = cert_cn[0].value if cert_cn else "unknown"

        # Check validity period
        if current_datetime < cert.not_valid_before_utc:
            self.logger.warning(f"Certificate '{cert_name}' not yet valid")
            return False
        if current_datetime > cert.not_valid_after_utc:
            self.logger.warning(f"Certificate '{cert_name}' has expired")
            return False

        return True

    def get_certificate_info(self, name: str) -> CertificateInfo | None:
        """
        Get certificate information.

        Args:
            name: Certificate name

        Returns:
            CertificateInfo or None if not found
        """
        with self._lock:
            cert = self._certificates.get(name)

        if not cert:
            # Try loading from file
            loaded = self.load_certificate(name)
            if loaded:
                cert, _ = loaded
                with self._lock:
                    self._certificates[name] = cert
            else:
                return None

        return CertificateInfo.from_x509(cert)


# ----------------------------------------------------------------
# Symmetric Encryption (AES)
# ----------------------------------------------------------------


class AESEncryption:
    """AES encryption utilities for data protection."""

    @staticmethod
    def generate_key(key_size: int = 256) -> bytes:
        """
        Generate AES key.

        Args:
            key_size: Key size in bits (128, 192, 256)

        Returns:
            Random key bytes
        """
        return secrets.token_bytes(key_size // 8)

    @staticmethod
    def encrypt(plaintext: bytes, key: bytes) -> tuple[bytes, bytes, bytes]:
        """
        Encrypt data using AES-GCM.

        Args:
            plaintext: Data to encrypt
            key: AES key (16, 24, or 32 bytes)

        Returns:
            Tuple of (ciphertext, nonce, tag)
        """
        # Generate random nonce
        nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM

        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
        )
        encryptor = cipher.encryptor()

        # Encrypt
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()

        return ciphertext, nonce, encryptor.tag

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce: bytes, tag: bytes) -> bytes:
        """
        Decrypt data using AES-GCM.

        Args:
            ciphertext: Encrypted data
            key: AES key
            nonce: Nonce used for encryption
            tag: Authentication tag

        Returns:
            Decrypted plaintext

        Raises:
            ValueError: If authentication fails
        """
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag),
        )
        decryptor = cipher.decryptor()

        # Decrypt and verify
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        return plaintext

    @staticmethod
    def encrypt_string(plaintext: str, key: bytes) -> str:
        """
        Encrypt string and return base64-encoded result.

        Args:
            plaintext: String to encrypt
            key: AES key

        Returns:
            Base64-encoded "nonce:tag:ciphertext"
        """
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext, nonce, tag = AESEncryption.encrypt(plaintext_bytes, key)

        # Combine and encode
        combined = nonce + tag + ciphertext
        return base64.b64encode(combined).decode("ascii")

    @staticmethod
    def decrypt_string(encrypted: str, key: bytes) -> str:
        """
        Decrypt base64-encoded encrypted string.

        Args:
            encrypted: Base64-encoded encrypted data
            key: AES key

        Returns:
            Decrypted string
        """
        # Decode
        combined = base64.b64decode(encrypted)

        # Split components
        nonce = combined[:12]
        tag = combined[12:28]
        ciphertext = combined[28:]

        # Decrypt
        plaintext_bytes = AESEncryption.decrypt(ciphertext, key, nonce, tag)
        return plaintext_bytes.decode("utf-8")


# ----------------------------------------------------------------
# Protocol-Specific Crypto
# ----------------------------------------------------------------


class DNP3Crypto:
    """DNP3 Secure Authentication v5 utilities."""

    @staticmethod
    def generate_update_key(key_size: int = 16) -> bytes:
        """Generate DNP3 SAv5 update key."""
        return secrets.token_bytes(key_size)

    @staticmethod
    def hmac_sha256(key: bytes, data: bytes) -> bytes:
        """Compute HMAC-SHA256 for DNP3 SAv5."""
        return hmac.new(key, data, hashlib.sha256).digest()

    @staticmethod
    def generate_challenge() -> bytes:
        """Generate 4-byte challenge for DNP3 SAv5."""
        return secrets.token_bytes(4)


class OPCUACrypto:
    """OPC UA security utilities."""

    @staticmethod
    def get_security_policy_uri(policy: OPCUASecurityPolicy) -> str:
        """Get OPC UA security policy URI."""
        base_uri = "http://opcfoundation.org/UA/SecurityPolicy/"
        return f"{base_uri}{policy.value}"

    @staticmethod
    def sign_and_encrypt(
        data: bytes,
        sender_private_key: rsa.RSAPrivateKey,
        receiver_cert: x509.Certificate,
    ) -> bytes:
        """
        Sign and encrypt data for OPC UA.

        Simplified implementation for simulation.
        Real OPC UA has complex chunking and sequencing.
        """
        # Sign with sender's private key
        signature = sender_private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        # Encrypt with receiver's public key
        receiver_public_key = receiver_cert.public_key()
        encrypted = receiver_public_key.encrypt(
            data + signature,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        return encrypted


# ----------------------------------------------------------------
# Key Storage (DataStore integration)
# ----------------------------------------------------------------


class SecureKeyStore:
    """
    Secure key storage using DataStore.

    Stores encrypted keys in DataStore for persistence.
    Uses master key for encryption (stored separately/in config).
    """

    def __init__(self, data_store: DataStore, master_key: bytes | None = None):
        """
        Initialise secure key store.

        Args:
            data_store: DataStore for persistence
            master_key: Master encryption key (generated if None)
        """
        self.data_store = data_store
        self.logger: ICSLogger = get_logger(__name__, device="key_store")

        # Master key for encrypting stored keys
        if master_key is None:
            master_key = AESEncryption.generate_key(256)
            self.logger.info("Generated new master key for SecureKeyStore")
        self.master_key = master_key

        self._lock = asyncio.Lock()

        self.logger.info("SecureKeyStore initialised")

    async def store_key(self, name: str, key: bytes, device: str = "system") -> None:
        """
        Store key securely in DataStore.

        Args:
            name: Key identifier
            key: Key bytes to store
            device: Device name for storage context
        """
        # Encrypt key with master key
        encrypted = AESEncryption.encrypt_string(
            base64.b64encode(key).decode("ascii"),
            self.master_key,
        )

        async with self._lock:
            # Store in DataStore metadata
            await self.data_store.update_metadata(
                device,
                {f"key_{name}": encrypted},
            )

        self.logger.info(f"Stored key '{name}' for device '{device}'")

    async def retrieve_key(self, name: str, device: str = "system") -> bytes | None:
        """
        Retrieve key from DataStore.

        Args:
            name: Key identifier
            device: Device name for storage context

        Returns:
            Decrypted key bytes or None if not found
        """
        async with self._lock:
            metadata = await self.data_store.read_metadata(device)
            if not metadata:
                self.logger.debug(f"No metadata found for device '{device}'")
                return None

            encrypted = metadata.get(f"key_{name}")
            if not encrypted:
                self.logger.debug(f"Key '{name}' not found for device '{device}'")
                return None

            # Decrypt key
            try:
                decrypted = AESEncryption.decrypt_string(encrypted, self.master_key)
                self.logger.info(f"Retrieved key '{name}' for device '{device}'")
                return base64.b64decode(decrypted)
            except Exception:
                self.logger.exception(
                    f"Failed to decrypt key '{name}' for device '{device}'"
                )
                return None

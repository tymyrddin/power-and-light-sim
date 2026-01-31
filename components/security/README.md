# Security Module

ICS security components for the power and light simulator, providing authentication, authorization, encryption, anomaly detection, and structured logging aligned with industrial standards.

## Components

| Module | Purpose | Standards |
|--------|---------|-----------|
| `logging_system.py` | Structured ICS logging with audit trails | IEC 62443, ISA 18.2 |
| `authentication.py` | RBAC authentication and authorization | IEC 62443 |
| `encryption.py` | Cryptographic utilities and key management | X.509, AES-GCM, RSA |
| `anomaly_detector.py` | Behavioral anomaly detection | Statistical analysis |

## Quick Start

```python
from components.security.logging_system import get_logger, EventSeverity, EventCategory
from components.security.authentication import AuthenticationManager, PermissionType
from components.security.encryption import CertificateManager, AESEncryption
from components.security.anomaly_detector import AnomalyDetector

# Logging
logger = get_logger(__name__, device="turbine_plc_1")
logger.info("Device started")
await logger.log_security("Access attempt detected", user="operator1")

# Authentication
auth = AuthenticationManager()
session_id = await auth.authenticate("operator1")
if await auth.authorize(session_id, PermissionType.CONTROL_SETPOINT, "turbine_1"):
    # Perform operation
    pass

# Encryption
key = AESEncryption.generate_key()
encrypted = AESEncryption.encrypt_string("sensitive data", key)
decrypted = AESEncryption.decrypt_string(encrypted, key)

# Anomaly Detection
detector = AnomalyDetector(data_store, system_state)
await detector.set_range_limit("sensor_1", "temperature", 0.0, 100.0)
anomalies = await detector.check_value("sensor_1", "temperature", 150.0)
```

## Module Details

### logging_system.py

Structured logging with ICS-specific features:

- **Event Severity** (IEC 62443): CRITICAL, ALERT, ERROR, WARNING, NOTICE, INFO, DEBUG
- **Event Categories**: SECURITY, SAFETY, PROCESS, ALARM, AUDIT, SYSTEM, COMMUNICATION, DIAGNOSTIC
- **Alarm Priority** (ISA 18.2): CRITICAL, HIGH, MEDIUM, LOW
- **Alarm States**: ACTIVE, ACKNOWLEDGED, CLEARED, SUPPRESSED

```python
from components.security.logging_system import (
    ICSLogger, get_logger, configure_logging,
    EventSeverity, EventCategory, AlarmPriority, AlarmState
)

# Configure global logging
configure_logging(log_dir="/var/log/ics", data_store=data_store)

# Get logger for a device
logger = get_logger(__name__, device="plc_1")

# Standard logging
logger.info("Normal operation")
logger.warning("Threshold approaching")

# ICS-specific logging
await logger.log_security("Unauthorized access attempt", severity=EventSeverity.ALERT)
await logger.log_alarm("High pressure", priority=AlarmPriority.HIGH, state=AlarmState.ACTIVE)
await logger.log_audit("Setpoint changed", user="operator1", action="write", result="ALLOWED")

# Retrieve audit trail
trail = await logger.get_audit_trail(limit=100, category=EventCategory.SECURITY)
```

### authentication.py

Role-based access control with session management:

**User Roles** (increasing privilege):
| Role | Permissions |
|------|-------------|
| VIEWER | View data, view alarms |
| OPERATOR | + Control setpoints, start/stop, mode changes |
| ENGINEER | + Configuration, programming, safety reset |
| SUPERVISOR | + Safety bypass, force, emergency shutdown |
| ADMIN | All permissions |

```python
from components.security.authentication import (
    AuthenticationManager, UserRole, PermissionType,
    quick_auth, verify_authorization
)

auth = AuthenticationManager()

# Create user
await auth.create_user("new_operator", UserRole.OPERATOR, full_name="Jane Doe")

# Authenticate
session_id = await auth.authenticate("operator1")

# Authorize single action
if await auth.authorize(session_id, PermissionType.CONTROL_SETPOINT, "turbine_1"):
    # Allowed
    pass

# Dual authorization (two-person rule) for critical operations
if await auth.authorize_with_dual_auth(
    session_id_1, session_id_2,
    PermissionType.SAFETY_BYPASS, "reactor_1"
):
    # Both users authorized
    pass

# Convenience functions for devices
if await verify_authorization("operator1", "control_setpoint", "turbine_1"):
    # Auto-authenticates and authorizes
    pass
```

### encryption.py

Cryptographic utilities for ICS protocols:

```python
from components.security.encryption import (
    CertificateManager, AESEncryption, SecureKeyStore,
    DNP3Crypto, OPCUACrypto,
    SecurityLevel, OPCUASecurityPolicy, DNP3AuthMode
)

# Certificate management
cert_mgr = CertificateManager(cert_dir=Path("./certs"))
cert, key = cert_mgr.generate_self_signed_cert("plc_1.local")
cert_mgr.save_certificate(cert, key, "plc_1")

# Validate certificate
if cert_mgr.validate_certificate(cert):
    # Certificate is valid (not expired)
    pass

# AES encryption
key = AESEncryption.generate_key(256)  # 256-bit key
encrypted = AESEncryption.encrypt_string("secret", key)
decrypted = AESEncryption.decrypt_string(encrypted, key)

# DNP3 Secure Authentication v5
update_key = DNP3Crypto.generate_update_key()
challenge = DNP3Crypto.generate_challenge()
mac = DNP3Crypto.hmac_sha256(update_key, data)

# OPC UA security
policy_uri = OPCUACrypto.get_security_policy_uri(OPCUASecurityPolicy.AES256_SHA256_RSAPSS)

# Secure key storage (encrypted in DataStore)
key_store = SecureKeyStore(data_store)
await key_store.store_key("session_key", session_key, device="plc_1")
retrieved_key = await key_store.retrieve_key("session_key", device="plc_1")
```

### anomaly_detector.py

Multi-method anomaly detection:

**Detection Methods**:
- Statistical (sigma threshold)
- Range violation
- Rate of change
- Alarm flood
- Pattern analysis (placeholder)
- Protocol anomalies (placeholder)

```python
from components.security.anomaly_detector import (
    AnomalyDetector, AnomalyType, AnomalySeverity
)

detector = AnomalyDetector(data_store, system_state)

# Configure baselines
await detector.add_baseline("plc_1", "temperature", learning_window=1000)
await detector.set_range_limit("plc_1", "pressure", min_value=0.0, max_value=150.0)
await detector.set_rate_of_change_limit("plc_1", "temperature", max_rate=5.0)

# Check values (returns list of detected anomalies)
anomalies = await detector.check_value("plc_1", "temperature", value)

# Check for alarm flooding
flood = await detector.check_alarm_flood("plc_1")

# Get detected anomalies
recent = await detector.get_recent_anomalies(limit=100, device="plc_1")
summary = await detector.get_anomaly_summary()

# Export learned baselines
baselines = await detector.export_baselines()
await detector.store_baselines_in_datastore()
```

## Integration

All modules integrate with core simulator components:

```
┌─────────────────────────────────────────────────────────────┐
│                      Security Module                         │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ logging      │ authentication│ encryption   │ anomaly        │
│ system       │              │              │ detector       │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                     Shared Dependencies                      │
├─────────────────┬─────────────────┬─────────────────────────┤
│ SimulationTime  │ DataStore       │ ConfigLoader            │
│ (timestamps)    │ (persistence)   │ (configuration)         │
└─────────────────┴─────────────────┴─────────────────────────┘
```

## Configuration

Security settings in `simulation.yml`:

```yaml
simulation:
  authentication:
    session_timeout_hours: 8  # null for no timeout

  security:
    security_level: "AUTHENTICATED"  # NONE, BASIC, ENCRYPTED, AUTHENTICATED, SIGNED
    rsa_key_size: 2048
    cert_validity_hours: 8760  # 1 year

  anomaly_detection:
    enabled: true
    sigma_threshold: 3.0
    learning_window: 1000
    alarm_flood_threshold: 10  # alarms per window
    alarm_flood_window: 60.0   # seconds
```

## Testing

```bash
# Run all security tests
python -m pytest tests/unit/security/ -v

# Run specific module tests
python -m pytest tests/unit/security/test_authentication.py -v

# Run with coverage
python -m pytest tests/unit/security/ --cov=components.security
```

## Standards Compliance

| Standard | Coverage |
|----------|----------|
| IEC 62443 | Security levels, event severity, RBAC |
| ISA 18.2 | Alarm priorities and states |
| IEC 62351 | Certificate management, encryption |
| DNP3 SAv5 | HMAC-SHA256, challenge-response |
| OPC UA | Security policies, signing/encryption |

## Architecture Notes

- **Singleton Pattern**: `AuthenticationManager` uses singleton for simulation-wide auth
- **Thread Safety**: Logger factory and auth manager are thread-safe
- **Async Operations**: All I/O operations are async for simulation compatibility
- **Audit Trails**: Security events automatically logged to `ICSLogger`
- **No Real Security**: This is a **simulation** - passwords are not validated, keys are stored unencrypted

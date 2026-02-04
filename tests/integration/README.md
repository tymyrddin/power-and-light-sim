# Integration Tests

Comprehensive integration tests for the UU Power & Light simulator that verify multiple components work together correctly.

## Test Structure

### `test_simulator_lifecycle.py`
Complete simulator lifecycle testing from cold start to shutdown:

**TestSimulatorLifecycle::test_complete_lifecycle**
- Phase 1: Cold Start - Initialize all components
- Phase 2: System Startup - Start devices in correct order
- Phase 3: Warm-up - Bring systems to operating conditions
- Phase 4: Steady State - Run normal operations
- Phase 5: Shutdown - Graceful system shutdown
- Phase 6: Verification - Final integrity checks

Tests 7 devices (3 physics engines, 4 PLCs, 3 workstations) across ~25 seconds of simulated time.

**TestSimulatorStability::test_extended_runtime**
- Extended runtime test (100s simulated)
- Verifies no memory leaks or state corruption
- Tests timing accuracy over long runs

## Running Tests

### Run all integration tests:
```bash
pytest tests/integration/
```

### Run specific test:
```bash
pytest tests/integration/test_simulator_lifecycle.py::TestSimulatorLifecycle::test_complete_lifecycle -v
```

### Run with detailed output:
```bash
pytest tests/integration/ -xvs
```

### Run only fast integration tests (exclude slow):
```bash
pytest tests/integration/ -m "integration and not slow"
```

### Run only slow tests:
```bash
pytest tests/integration/ -m slow
```

## Test Markers

- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.slow` - Tests that take >10 seconds
- `@pytest.mark.asyncio` - Async tests (all integration tests use this)

## Expected Runtime

- **test_complete_lifecycle**: ~2-5 seconds wall time
- **test_extended_runtime**: ~10-15 seconds wall time

## Coverage

Integration tests cover:
- ✓ Device lifecycle (start/stop)
- ✓ Physics engine integration
- ✓ PLC communication with physics
- ✓ Safety system coordination
- ✓ SCADA and HMI monitoring
- ✓ Protocol communication
- ✓ State management
- ✓ Telemetry flow
- ✓ Clean shutdown procedures
- ✓ Extended stability

## Adding New Integration Tests

When adding integration tests:

1. Mark with `@pytest.mark.integration`
2. Mark with `@pytest.mark.slow` if >10s runtime
3. Use `@pytest.mark.asyncio` for async tests
4. Clean up resources in try/finally blocks
5. Provide detailed phase documentation
6. Print progress for long-running tests

Example:
```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_scenario(self, system_infrastructure):
    \"\"\"Test description.\"\"\"
    system_state, data_store = system_infrastructure
    devices = []

    try:
        # Test implementation
        print("[PHASE 1] Description")
        # ...
    finally:
        # Cleanup
        for device in devices:
            if device.is_running():
                await device.stop()
```

## Troubleshooting

**Test hangs:**
- Check for devices not stopped in cleanup
- Verify no infinite loops in physics updates
- Check SimulationTime not blocked

**Test fails inconsistently:**
- May be timing-sensitive
- Increase sleep() durations
- Check for race conditions in async code

**Memory issues:**
- Verify all devices stopped in finally blocks
- Check SimulationTime reset in fixtures
- Look for circular references

## Future Integration Tests

Planned additions:
- Protocol server integration (Modbus, S7, OPC UA)
- Attack scenario integration (run actual exploit scripts)
- Network communication tests
- Multi-protocol coordination
- Fault injection and recovery

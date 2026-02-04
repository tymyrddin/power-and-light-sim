# tests/integration/__init__.py
"""
Integration tests for UU Power & Light simulator.

These tests verify that multiple components work together correctly
as a complete system. They are more comprehensive than unit tests
and test real-world usage scenarios.

Test Categories:
- Lifecycle tests: Full simulator startup/shutdown cycles
- Protocol tests: Multi-device protocol communication
- Scenario tests: Attack/defence scenarios
- Stability tests: Extended runtime and stress testing

Running Integration Tests:
    pytest tests/integration/                    # All integration tests
    pytest tests/integration/ -m integration     # Tagged as integration
    pytest tests/integration/ -m slow            # Long-running tests only
    pytest tests/integration/ -k lifecycle       # Lifecycle tests only

Note: Integration tests are slower than unit tests but provide
higher confidence in system integration.
"""

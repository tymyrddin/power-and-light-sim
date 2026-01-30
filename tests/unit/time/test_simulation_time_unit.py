# tests/unit/time/test_simulation_time.py
"""Comprehensive tests for SimulationTime component.

This is Level 0 in our dependency tree - SimulationTime has NO dependencies
on other simulator components, making it the perfect foundation to test first.

Test Coverage:
- Time initialisation and configuration
- Time scaling (realtime vs accelerated)
- Pause/resume behaviour with duration tracking
- Time tracking accuracy across modes
- Thread safety and concurrent access
- Edge cases and error handling
- Singleton behaviour
"""

import asyncio
import pytest
import time as wall_time

from components.time.simulation_time import (
    SimulationTime,
    TimeMode,
    wait_simulation_time,
    get_simulation_delta,
)


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestSimulationTimeInitialization:
    """Test SimulationTime initialization and configuration."""

    def test_singleton_behavior(self, setup_config_files):
        """Verify SimulationTime follows singleton pattern.

        WHY: Only one time authority should exist in the simulation.
        Multiple instances would cause timing inconsistencies.
        """
        setup_config_files()

        instance1 = SimulationTime()
        instance2 = SimulationTime()

        assert instance1 is instance2, "SimulationTime should be singleton"
        assert id(instance1) == id(instance2)

    def test_default_configuration(self, setup_config_files):
        """Test initialisation with default configuration.

        WHY: Ensures sensible defaults when no config is provided.
        """
        setup_config_files()

        sim_time = SimulationTime()
        sim_time.reset_for_testing()  # Reset to fresh state

        assert sim_time.state.simulation_time == 0.0
        assert sim_time.state.speed_multiplier == 1.0
        assert sim_time.state.mode == TimeMode.REALTIME
        assert sim_time.state.update_interval == 0.01
        assert not sim_time._running

    def test_accelerated_configuration(self, setup_config_files, accelerated_config):
        """Test initialisation with accelerated time configuration.

        WHY: Accelerated mode is critical for rapid testing scenarios.
        """
        setup_config_files(accelerated_config)

        sim_time = SimulationTime()
        sim_time.reset_for_testing()

        assert sim_time.state.mode == TimeMode.ACCELERATED
        assert sim_time.state.speed_multiplier == 10.0

    def test_invalid_update_interval_uses_default(self, setup_config_files):
        """Test that invalid update intervals fall back to defaults.

        WHY: Prevents simulation from breaking with bad config values.
        """
        invalid_config = {
            "simulation": {
                "runtime": {
                    "update_interval": -0.01,  # Invalid
                    "realtime": True,
                    "time_acceleration": 1.0,
                }
            }
        }
        setup_config_files(invalid_config)

        sim_time = SimulationTime()
        sim_time.reset_for_testing()

        assert sim_time.state.update_interval == 0.01, "Should use default"

    def test_invalid_speed_multiplier_uses_default(self, setup_config_files):
        """Test that invalid speed multipliers fall back to defaults.

        WHY: Prevents time from running backwards or at zero speed.
        """
        invalid_config = {
            "simulation": {
                "runtime": {
                    "time_acceleration": -5.0,  # Invalid
                    "realtime": True,
                    "update_interval": 0.01,
                }
            }
        }
        setup_config_files(invalid_config)

        sim_time = SimulationTime()
        sim_time.reset_for_testing()

        assert sim_time.state.speed_multiplier == 1.0, "Should use default"

    def test_excessive_speed_multiplier_capped(self, setup_config_files):
        """Test that excessive speed multipliers are capped at maximum.

        WHY: Prevents numerical instability and unrealistic simulation speeds.
        """
        excessive_config = {
            "simulation": {
                "runtime": {
                    "time_acceleration": 999999.0,  # Excessive
                    "realtime": False,
                    "update_interval": 0.01,
                }
            }
        }
        setup_config_files(excessive_config)

        sim_time = SimulationTime()
        sim_time.reset_for_testing()

        assert sim_time.state.speed_multiplier <= SimulationTime._MAX_SPEED_MULTIPLIER


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestSimulationTimeLifecycle:
    """Test SimulationTime lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_initializes_time(self, clean_simulation_time):
        """Test that start() properly initialises time tracking.

        WHY: Start is the entry point - must set up all state correctly.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        assert sim_time._running
        assert sim_time.state.simulation_time == 0.0
        assert sim_time.state.wall_time_start > 0
        assert sim_time._update_task is not None

    @pytest.mark.asyncio
    async def test_start_creates_time_loop_for_realtime(self, clean_simulation_time):
        """Test that REALTIME mode starts automatic time loop.

        WHY: REALTIME and ACCELERATED modes need continuous time updates.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        assert sim_time._update_task is not None
        assert not sim_time._update_task.done()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, clean_simulation_time):
        """Test that calling start() multiple times is safe.

        WHY: Prevents crashes from accidental double-start.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.start()  # Should not crash or create duplicate tasks

        assert sim_time._running

    @pytest.mark.asyncio
    async def test_stop_cancels_time_loop(self, clean_simulation_time):
        """Test that stop() properly cancels the time loop.

        WHY: Clean shutdown prevents resource leaks and orphaned tasks.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.05)  # Let loop run briefly
        await sim_time.stop()

        assert not sim_time._running
        assert sim_time._update_task is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, clean_simulation_time):
        """Test that calling stop() multiple times is safe.

        WHY: Clean-up code often calls stop() defensively.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.stop()
        await sim_time.stop()  # Should not crash

        assert not sim_time._running

    @pytest.mark.asyncio
    async def test_reset_clears_time_but_preserves_config(self, clean_simulation_time_with_config):
        """Test that reset() clears time but keeps configuration.

        WHY: Reset is used between simulation runs - config should persist.
        """
        config = {
            "simulation": {
                "runtime": {
                    "realtime": False,
                    "time_acceleration": 5.0,
                    "update_interval": 0.01,
                }
            }
        }
        sim_time = await clean_simulation_time_with_config(config)

        await sim_time.start()
        await asyncio.sleep(0.1)  # Let time accumulate

        original_speed = sim_time.state.speed_multiplier
        original_mode = sim_time.state.mode

        await sim_time.reset()

        assert sim_time.state.simulation_time == 0.0
        assert sim_time.state.speed_multiplier == original_speed
        assert sim_time.state.mode == original_mode

        await sim_time.stop()  # Cleanup


# ================================================================
# TIME QUERY TESTS
# ================================================================
class TestSimulationTimeQueries:
    """Test time query methods."""

    @pytest.mark.asyncio
    async def test_now_returns_current_time(self, clean_simulation_time):
        """Test that now() returns current simulation time.

        WHY: Most basic time query - must be accurate.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        initial = sim_time.now()

        await asyncio.sleep(0.1)

        later = sim_time.now()
        assert later > initial

    @pytest.mark.asyncio
    async def test_delta_calculates_difference(self, clean_simulation_time):
        """Test that delta() correctly calculates time differences.

        WHY: Components need to measure elapsed time for physics updates.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        t1 = sim_time.now()
        await asyncio.sleep(0.1)
        t2 = sim_time.now()

        delta = sim_time.delta(t1)
        expected_delta = t2 - t1

        assert abs(delta - expected_delta) < 0.01

    @pytest.mark.asyncio
    async def test_elapsed_equals_now(self, clean_simulation_time):
        """Test that elapsed() returns same value as now() from start.

        WHY: They measure the same thing - time since start/reset.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.1)

        assert sim_time.elapsed() == sim_time.now()

    @pytest.mark.asyncio
    async def test_wall_elapsed_tracks_real_time(self, clean_simulation_time):
        """Test that wall_elapsed() tracks actual wall-clock time.

        WHY: Need to measure real-time performance regardless of time scaling.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        start = wall_time.time()
        await asyncio.sleep(0.1)
        end = wall_time.time()

        wall_elapsed = sim_time.wall_elapsed()
        actual_elapsed = end - start

        # Should be approximately equal (within 50ms tolerance)
        assert abs(wall_elapsed - actual_elapsed) < 0.05

    @pytest.mark.asyncio
    async def test_speed_returns_current_multiplier(self, clean_simulation_time_with_config):
        """Test that speed() returns current speed multiplier.

        WHY: Components need to know time scaling for calculations.
        """
        config = {
            "simulation": {
                "runtime": {
                    "time_acceleration": 5.0,
                    "realtime": False,
                    "update_interval": 0.01,
                }
            }
        }
        sim_time = await clean_simulation_time_with_config(config)

        assert sim_time.speed() == 5.0

        await sim_time.stop()  # Cleanup

    @pytest.mark.asyncio
    async def test_is_paused_reflects_pause_state(self, clean_simulation_time):
        """Test that is_paused() accurately reflects pause state.

        WHY: Components need to know if time is paused to handle correctly.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        assert not sim_time.is_paused()

        await sim_time.pause()
        assert sim_time.is_paused()

        await sim_time.resume()
        assert not sim_time.is_paused()


# ================================================================
# TIME PROGRESSION TESTS
# ================================================================
class TestSimulationTimeProgression:
    """Test time progression in different modes."""

    @pytest.mark.asyncio
    async def test_realtime_mode_progresses_naturally(
            self, clean_simulation_time, assert_time_approximately
    ):
        """Test that REALTIME mode advances at 1:1 ratio with wall time.

        WHY: REALTIME mode must match wall-clock for realistic simulation.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.2)  # Wait 200ms

        elapsed = sim_time.now()
        assert_time_approximately(elapsed, 0.2, tolerance=0.05)

    @pytest.mark.asyncio
    async def test_accelerated_mode_progresses_faster(
            self, clean_simulation_time_with_config, assert_time_approximately
    ):
        """Test that ACCELERATED mode advances faster than wall time.

        WHY: Accelerated mode enables rapid testing of long-duration scenarios.
        """
        config = {
            "simulation": {
                "runtime": {
                    "realtime": False,
                    "time_acceleration": 10.0,
                    "update_interval": 0.01,
                }
            }
        }
        sim_time = await clean_simulation_time_with_config(config)

        await sim_time.start()
        await asyncio.sleep(0.2)  # Wait 200ms wall time

        elapsed = sim_time.now()
        # Should be approximately 2.0s sim time (10x acceleration)
        assert_time_approximately(elapsed, 2.0, tolerance=0.3)

        await sim_time.stop()  # Cleanup

    @pytest.mark.asyncio
    async def test_paused_mode_does_not_progress(
            self, clean_simulation_time
    ):
        """Test that paused time does not advance.

        WHY: Pause is used for debugging and inspection - time must freeze.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.05)

        await sim_time.pause()
        paused_time = sim_time.now()

        await asyncio.sleep(0.1)  # Wait while paused

        assert sim_time.now() == paused_time, "Time should not advance while paused"

    @pytest.mark.asyncio
    async def test_stepped_mode_requires_manual_stepping(
            self, clean_simulation_time
    ):
        """Test that STEPPED mode only advances via step() calls.

        WHY: STEPPED mode gives precise control for deterministic testing.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()
        initial_time = sim_time.now()

        await asyncio.sleep(0.1)  # Time should not auto-advance
        assert sim_time.now() == initial_time

        await sim_time.step(5.0)  # Manually advance 5 seconds
        assert sim_time.now() == initial_time + 5.0


# ================================================================
# PAUSE/RESUME TESTS
# ================================================================
class TestSimulationTimePauseResume:
    """Test pause and resume functionality."""

    @pytest.mark.asyncio
    async def test_pause_stops_time_progression(
            self, clean_simulation_time
    ):
        """Test that pause() stops time from advancing.

        WHY: Core pause functionality must work correctly.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.05)

        await sim_time.pause()
        paused_time = sim_time.now()

        await asyncio.sleep(0.1)

        assert sim_time.now() == paused_time

    @pytest.mark.asyncio
    async def test_resume_restarts_time_progression(
            self, clean_simulation_time
    ):
        """Test that resume() restarts time after pause.

        WHY: Must be able to unpause and continue simulation.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.pause()
        paused_time = sim_time.now()

        await sim_time.resume()
        await asyncio.sleep(0.1)

        assert sim_time.now() > paused_time

    @pytest.mark.asyncio
    async def test_pause_duration_tracked(
            self, clean_simulation_time
    ):
        """Test that pause duration is properly tracked.

        WHY: Need to distinguish between sim time and wall time when paused.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.05)

        await sim_time.pause()
        await asyncio.sleep(0.1)  # Pause for 100ms
        await sim_time.resume()

        # Total pause duration should be approximately 100ms
        assert 0.08 <= sim_time.state.total_pause_duration <= 0.15

    @pytest.mark.asyncio
    async def test_multiple_pause_resume_cycles(
            self, clean_simulation_time
    ):
        """Test multiple pause/resume cycles accumulate duration correctly.

        WHY: Simulations may pause/resume many times during execution.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        # First pause cycle
        await sim_time.pause()
        await asyncio.sleep(0.05)
        await sim_time.resume()

        # Second pause cycle
        await sim_time.pause()
        await asyncio.sleep(0.05)
        await sim_time.resume()

        # Total pause should be approximately 100ms
        assert sim_time.state.total_pause_duration >= 0.08

    @pytest.mark.asyncio
    async def test_pause_when_already_paused_is_safe(
            self, clean_simulation_time
    ):
        """Test that pausing when already paused doesn't break anything.

        WHY: Defensive programming - multiple pause calls should be safe.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.pause()
        await sim_time.pause()  # Should be safe

        assert sim_time.is_paused()

    @pytest.mark.asyncio
    async def test_resume_when_not_paused_is_safe(
            self, clean_simulation_time
    ):
        """Test that resuming when not paused doesn't break anything.

        WHY: Defensive programming - multiple resume calls should be safe.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.resume()  # Should be safe

        assert not sim_time.is_paused()


# ================================================================
# SPEED CONTROL TESTS
# ================================================================
class TestSimulationTimeSpeedControl:
    """Test speed multiplier control."""

    @pytest.mark.asyncio
    async def test_set_speed_changes_multiplier(
            self, clean_simulation_time
    ):
        """Test that set_speed() changes the speed multiplier.

        WHY: Need to dynamically adjust simulation speed.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.set_speed(5.0)

        assert sim_time.speed() == 5.0

    @pytest.mark.asyncio
    async def test_set_speed_maintains_time_continuity(
            self, clean_simulation_time, assert_time_approximately
    ):
        """Test that changing speed doesn't cause time jumps.

        WHY: Speed changes must be smooth - no discontinuities in time.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.1)

        time_before_change = sim_time.now()
        await sim_time.set_speed(10.0)
        time_after_change = sim_time.now()

        # Time should be continuous (no jump)
        assert_time_approximately(time_after_change, time_before_change, tolerance=0.01)

    @pytest.mark.asyncio
    async def test_set_speed_affects_future_progression(
            self, clean_simulation_time
    ):
        """Test that new speed affects subsequent time progression.

        WHY: Speed change must actually change the rate of time flow.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.set_speed(10.0)

        time_before = sim_time.now()
        await asyncio.sleep(0.1)  # 100ms wall time
        time_after = sim_time.now()

        elapsed = time_after - time_before
        # Should be approximately 1.0s sim time (10x speed)
        assert 0.7 <= elapsed <= 1.3

    @pytest.mark.asyncio
    async def test_set_speed_rejects_zero(
            self, clean_simulation_time
    ):
        """Test that set_speed() rejects zero multiplier.

        WHY: Zero speed would freeze time permanently - not allowed.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        with pytest.raises(ValueError, match="must be > 0"):
            await sim_time.set_speed(0.0)

    @pytest.mark.asyncio
    async def test_set_speed_rejects_negative(
            self, clean_simulation_time
    ):
        """Test that set_speed() rejects negative multiplier.

        WHY: Negative speed (time reversal) not supported.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        with pytest.raises(ValueError, match="must be > 0"):
            await sim_time.set_speed(-1.0)

    @pytest.mark.asyncio
    async def test_set_speed_rejects_excessive_values(
            self, clean_simulation_time
    ):
        """Test that set_speed() rejects values above maximum.

        WHY: Excessive speeds cause numerical instability.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        with pytest.raises(ValueError, match="exceeds maximum"):
            await sim_time.set_speed(999999.0)


# ================================================================
# STEPPED MODE TESTS
# ================================================================
class TestSimulationTimeSteppedMode:
    """Test manual stepping functionality."""

    @pytest.mark.asyncio
    async def test_step_advances_time_by_delta(
            self, clean_simulation_time
    ):
        """Test that step() advances time by specified amount.

        WHY: Core functionality of STEPPED mode.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()
        initial = sim_time.now()

        await sim_time.step(5.0)

        assert sim_time.now() == initial + 5.0

    @pytest.mark.asyncio
    async def test_step_accumulates_multiple_calls(
            self, clean_simulation_time
    ):
        """Test that multiple step() calls accumulate.

        WHY: Stepping is used iteratively - must accumulate correctly.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()

        await sim_time.step(1.0)
        await sim_time.step(2.0)
        await sim_time.step(3.0)

        assert sim_time.now() == 6.0

    @pytest.mark.asyncio
    async def test_step_rejects_negative_delta(
            self, clean_simulation_time
    ):
        """Test that step() rejects negative time steps.

        WHY: Cannot step backwards in time.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()

        with pytest.raises(ValueError, match="Cannot step negative time"):
            await sim_time.step(-1.0)

    @pytest.mark.asyncio
    async def test_step_only_works_in_stepped_or_paused_mode(
            self, clean_simulation_time
    ):
        """Test that step() only works in STEPPED or PAUSED mode.

        WHY: Manual stepping conflicts with auto-progression modes.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.REALTIME

        await sim_time.start()

        with pytest.raises(RuntimeError, match="only valid in STEPPED or PAUSED mode"):
            await sim_time.step(1.0)

    @pytest.mark.asyncio
    async def test_step_works_in_stepped_mode(
            self, clean_simulation_time
    ):
        """Test that step() advances time in STEPPED mode.

        WHY: STEPPED mode allows precise control for deterministic testing.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED  # Set mode to STEPPED

        await sim_time.start()
        initial = sim_time.now()

        await sim_time.step(1.0)

        assert sim_time.now() == initial + 1.0

    @pytest.mark.asyncio
    async def test_step_works_in_paused_mode(
            self, clean_simulation_time
    ):
        """Test that step() advances time when mode is PAUSED.

        WHY: PAUSED mode with stepping is useful for frame-by-frame debugging.
        Note: Requires mode to be TimeMode.PAUSED, not just paused=True flag.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.PAUSED  # Set mode to PAUSED

        await sim_time.start()
        initial = sim_time.now()

        await sim_time.step(1.0)

        assert sim_time.now() == initial + 1.0


# ================================================================
# STATUS TESTS
# ================================================================
class TestSimulationTimeStatus:
    """Test status reporting functionality."""

    @pytest.mark.asyncio
    async def test_get_status_returns_complete_state(
            self, clean_simulation_time
    ):
        """Test that get_status() returns all relevant state information.

        WHY: Status used for monitoring and debugging - must be comprehensive.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await asyncio.sleep(0.05)

        status = await sim_time.get_status()

        assert "simulation_time" in status
        assert "wall_time_elapsed" in status
        assert "mode" in status
        assert "speed_multiplier" in status
        assert "paused" in status
        assert "total_pause_duration" in status
        assert "ratio" in status

    @pytest.mark.asyncio
    async def test_get_status_ratio_matches_speed_multiplier(
            self, clean_simulation_time_with_config, assert_time_approximately
    ):
        """Test that status ratio reflects actual time scaling.

        WHY: Ratio is key metric for monitoring time progression accuracy.
        """
        config = {
            "simulation": {
                "runtime": {
                    "realtime": False,
                    "time_acceleration": 5.0,
                    "update_interval": 0.01,
                }
            }
        }
        sim_time = await clean_simulation_time_with_config(config)

        await sim_time.start()
        await asyncio.sleep(0.2)  # Let time accumulate

        status = await sim_time.get_status()

        # Ratio should be close to speed multiplier
        assert_time_approximately(status["ratio"], 5.0, tolerance=1.0)

        await sim_time.stop()  # Cleanup


# ================================================================
# CONVENIENCE FUNCTION TESTS
# ================================================================
class TestSimulationTimeConvenienceFunctions:
    """Test convenience functions for time operations."""

    @pytest.mark.asyncio
    async def test_wait_simulation_time_waits_correct_duration(
            self, clean_simulation_time, assert_time_approximately
    ):
        """Test that wait_simulation_time() waits for simulation time.

        WHY: Common pattern for time-based delays in simulation.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        start = sim_time.now()

        await wait_simulation_time(0.5)

        end = sim_time.now()
        elapsed = end - start

        assert_time_approximately(elapsed, 0.5, tolerance=0.1)

    @pytest.mark.asyncio
    async def test_wait_simulation_time_respects_acceleration(
            self, clean_simulation_time_with_config
    ):
        """Test that wait_simulation_time() works with accelerated time.

        WHY: Must work correctly across all time modes.
        """
        config = {
            "simulation": {
                "runtime": {
                    "realtime": False,
                    "time_acceleration": 10.0,
                    "update_interval": 0.01,
                }
            }
        }
        sim_time = await clean_simulation_time_with_config(config)

        await sim_time.start()
        start = sim_time.now()

        await wait_simulation_time(1.0)  # 1 sim second

        end = sim_time.now()
        elapsed = end - start

        # Should wait approximately 1.0 sim seconds
        assert 0.8 <= elapsed <= 1.2

        await sim_time.stop()  # Cleanup

    @pytest.mark.asyncio
    async def test_wait_simulation_time_handles_pause(
            self, clean_simulation_time
    ):
        """Test that wait_simulation_time() waits during pauses.

        WHY: Must handle paused state correctly.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        # Start waiting, then pause in background
        async def pause_briefly():
            await asyncio.sleep(0.05)
            await sim_time.pause()
            await asyncio.sleep(0.1)
            await sim_time.resume()

        pause_task = asyncio.create_task(pause_briefly())

        start = sim_time.now()
        await wait_simulation_time(0.2)
        end = sim_time.now()

        await pause_task

        # Should still wait for 0.2 sim seconds despite pause
        assert end - start >= 0.18

    @pytest.mark.asyncio
    async def test_wait_simulation_time_rejects_negative(
            self, clean_simulation_time
    ):
        """Test that wait_simulation_time() rejects negative durations.

        WHY: Cannot wait for negative time.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        with pytest.raises(ValueError, match="Cannot wait negative time"):
            await wait_simulation_time(-1.0)

    @pytest.mark.asyncio
    async def test_wait_simulation_time_zero_returns_immediately(
            self, clean_simulation_time
    ):
        """Test that waiting for zero time returns immediately.

        WHY: Edge case that should be handled efficiently.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        start = wall_time.time()

        await wait_simulation_time(0.0)

        end = wall_time.time()

        # Should return almost instantly
        assert end - start < 0.01

    def test_get_simulation_delta_calculates_correctly(
            self, clean_simulation_time
    ):
        """Test that get_simulation_delta() helper works correctly.

        WHY: Convenient helper for common delta calculations.
        """
        sim_time = clean_simulation_time
        sim_time.state.simulation_time = 10.0

        delta = get_simulation_delta(7.0)

        assert delta == 3.0


# ================================================================
# CONCURRENCY TESTS
# ================================================================
class TestSimulationTimeConcurrency:
    """Test thread-safety and concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_are_safe(
            self, clean_simulation_time
    ):
        """Test that multiple coroutines can safely read time.

        WHY: Many components will query time concurrently.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        async def read_time():
            for _ in range(100):
                _ = sim_time.now()
                await asyncio.sleep(0.001)

        # Run multiple readers concurrently
        await asyncio.gather(*[read_time() for _ in range(10)])

        # Should complete without errors

    @pytest.mark.asyncio
    async def test_concurrent_speed_changes_are_safe(
            self, clean_simulation_time
    ):
        """Test that concurrent speed changes don't cause corruption.

        WHY: Multiple components might try to change speed.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        async def change_speed():
            for i in range(10):
                speed = 1.0 + (i % 5)
                await sim_time.set_speed(speed)
                await asyncio.sleep(0.01)

        # Run concurrent speed changes
        await asyncio.gather(*[change_speed() for _ in range(3)])

        # Should complete without errors or corruption
        assert sim_time.speed() > 0

    @pytest.mark.asyncio
    async def test_concurrent_pause_resume_are_safe(
            self, clean_simulation_time
    ):
        """Test that concurrent pause/resume operations are safe.

        WHY: Multiple components might try to pause/resume.
        """
        sim_time = clean_simulation_time

        await sim_time.start()

        async def toggle_pause():
            for _ in range(10):
                if sim_time.is_paused():
                    await sim_time.resume()
                else:
                    await sim_time.pause()
                await asyncio.sleep(0.01)

        # Run concurrent pause/resume
        await asyncio.gather(*[toggle_pause() for _ in range(3)])

        # Should complete without deadlock or corruption


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestSimulationTimeEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_small_time_steps(
            self, clean_simulation_time
    ):
        """Test handling of very small time steps.

        WHY: Physics updates may use microsecond-level precision.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()

        # Step by 1 microsecond
        await sim_time.step(0.000001)

        assert sim_time.now() == 0.000001

    @pytest.mark.asyncio
    async def test_very_large_time_values(
            self, clean_simulation_time
    ):
        """Test handling of very large simulation times.

        WHY: Long-running simulations accumulate large time values.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()

        # Advance to 1 million seconds (11.5 days)
        await sim_time.step(1_000_000.0)

        assert sim_time.now() == 1_000_000.0

    @pytest.mark.asyncio
    async def test_fractional_speed_multipliers(
            self, clean_simulation_time
    ):
        """Test that fractional speeds (slow motion) work correctly.

        WHY: Slow motion useful for detailed observation.
        """
        sim_time = clean_simulation_time

        await sim_time.start()
        await sim_time.set_speed(0.1)  # 10x slower

        time_before = sim_time.now()
        await asyncio.sleep(0.1)  # 100ms wall time
        time_after = sim_time.now()

        elapsed = time_after - time_before
        # Should be approximately 10ms sim time
        assert 0.005 <= elapsed <= 0.02

    @pytest.mark.asyncio
    async def test_time_precision_maintained(
            self, clean_simulation_time
    ):
        """Test that time precision is maintained through operations.

        WHY: Floating point errors can accumulate over time.
        """
        sim_time = clean_simulation_time
        sim_time.state.mode = TimeMode.STEPPED

        await sim_time.start()

        # Many small steps
        for _ in range(1000):
            await sim_time.step(0.001)

        # Should equal 1.0 within floating point tolerance
        assert abs(sim_time.now() - 1.0) < 1e-9

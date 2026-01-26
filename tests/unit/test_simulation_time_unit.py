import pytest
from components.time.simulation_time import (
    SimulationTime,
    TimeMode,
    wait_simulation_time,
    get_simulation_delta,
)


@pytest.mark.asyncio
async def test_initial_state_from_config(mock_config_realtime):
    sim = SimulationTime()

    assert sim.state.mode == TimeMode.REALTIME
    assert sim.state.speed_multiplier == 1.0
    assert sim.state.update_interval == 0.01
    assert sim.now() == 0.0


@pytest.mark.asyncio
async def test_set_speed_validation(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    with pytest.raises(ValueError):
        await sim.set_speed(0)

    with pytest.raises(ValueError):
        await sim.set_speed(-1)

    with pytest.raises(ValueError):
        await sim.set_speed(10_000)

    await sim.set_speed(5.0)
    assert sim.speed() == 5.0


@pytest.mark.asyncio
async def test_pause_and_resume_state(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    assert not sim.is_paused()

    await sim.pause()
    assert sim.is_paused()
    assert sim.state.pause_start is not None

    await sim.resume()
    assert not sim.is_paused()
    assert sim.state.pause_start is None
    assert sim.state.total_pause_duration >= 0.0


@pytest.mark.asyncio
async def test_step_only_allowed_in_correct_modes(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    with pytest.raises(RuntimeError):
        await sim.step(1.0)

    sim.state.mode = TimeMode.STEPPED
    await sim.step(2.5)
    assert sim.now() == pytest.approx(2.5)

    with pytest.raises(ValueError):
        await sim.step(-1.0)


def test_delta_and_elapsed(mock_config_realtime):
    sim = SimulationTime()
    sim.state.simulation_time = 10.0

    last = 4.0
    assert sim.delta(last) == 6.0
    assert sim.elapsed() == 10.0


@pytest.mark.asyncio
async def test_wait_simulation_time_validation(mock_config_realtime):
    with pytest.raises(ValueError):
        await wait_simulation_time(-1)

    # zero should return immediately
    await wait_simulation_time(0)


def test_get_simulation_delta(mock_config_realtime):
    sim = SimulationTime()
    sim.state.simulation_time = 12.0

    assert get_simulation_delta(7.0) == 5.0

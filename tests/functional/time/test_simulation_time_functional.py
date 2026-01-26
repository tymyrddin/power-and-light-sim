import asyncio
import pytest
from components.time.simulation_time import SimulationTime, TimeMode, wait_simulation_time


@pytest.mark.asyncio
async def test_realtime_progression(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    start = sim.now()
    await asyncio.sleep(0.05)
    end = sim.now()

    assert end > start
    assert 0.03 <= (end - start) <= 0.2

    await sim.stop()


@pytest.mark.asyncio
async def test_accelerated_time_progression(mock_config_accelerated):
    sim = SimulationTime()
    await sim.start()

    start = sim.now()
    await asyncio.sleep(0.05)
    end = sim.now()

    # 10x acceleration → ~0.5s simulated
    assert end - start >= 0.3

    await sim.stop()


@pytest.mark.asyncio
async def test_pause_stops_time(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    await asyncio.sleep(0.03)
    await sim.pause()

    frozen = sim.now()
    await asyncio.sleep(0.05)

    assert sim.now() == pytest.approx(frozen, abs=0.01)

    await sim.resume()
    await asyncio.sleep(0.03)

    assert sim.now() > frozen
    await sim.stop()


@pytest.mark.asyncio
async def test_wait_simulation_time_respects_acceleration(mock_config_accelerated):
    sim = SimulationTime()
    await sim.start()

    start_wall = asyncio.get_event_loop().time()
    await wait_simulation_time(1.0)
    elapsed_wall = asyncio.get_event_loop().time() - start_wall

    # At 10x speed, 1 sim second ≈ 0.1 wall seconds
    assert elapsed_wall < 0.5

    await sim.stop()


@pytest.mark.asyncio
async def test_wait_simulation_time_respects_pause(mock_config_realtime):
    sim = SimulationTime()
    await sim.start()

    async def pause_soon():
        await asyncio.sleep(0.05)
        await sim.pause()
        await asyncio.sleep(0.05)
        await sim.resume()

    asyncio.create_task(pause_soon())

    start = sim.now()
    await wait_simulation_time(0.1)
    end = sim.now()

    assert end - start >= 0.1
    await sim.stop()

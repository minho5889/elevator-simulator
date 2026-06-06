# tests/test_traffic.py
"""Tests for the stochastic TrafficGenerator and traffic profiles."""

import pytest
import random
from elevatorsim.core.traffic import TrafficGenerator
from elevatorsim.core.passenger import Passenger

def test_traffic_generator_validation():
    """Verify invalid profile names raise ValueError."""
    with pytest.raises(ValueError):
        TrafficGenerator(profile="INVALID_PROFILE")


def test_uniform_traffic_profile():
    """Verify uniform profile obeys source/target floor boundaries and inequality."""
    rng = random.Random(42)
    tg = TrafficGenerator(num_floors=5, arrival_rate=1.0, profile="UNIFORM")
    
    for tick in range(1, 50):
        passengers = tg.generate(tick, rng)
        assert len(passengers) == 1
        p = passengers[0]
        
        assert isinstance(p, Passenger)
        assert p.spawn_time == tick
        assert 0 <= p.source_floor < 5
        assert 0 <= p.target_floor < 5
        assert p.source_floor != p.target_floor


def test_down_peak_traffic_profile():
    """Verify morning rush profile directs all passengers from upper floors to lobby (floor 0)."""
    rng = random.Random(100)
    tg = TrafficGenerator(num_floors=5, arrival_rate=1.0, profile="DOWN_PEAK")
    
    for tick in range(1, 50):
        passengers = tg.generate(tick, rng)
        assert len(passengers) == 1
        p = passengers[0]
        
        assert p.source_floor >= 1
        assert p.target_floor == 0
        assert p.direction == -1  # DOWN


def test_up_peak_traffic_profile():
    """Verify evening rush profile directs all passengers from lobby (floor 0) to upper floors."""
    rng = random.Random(200)
    tg = TrafficGenerator(num_floors=5, arrival_rate=1.0, profile="UP_PEAK")
    
    for tick in range(1, 50):
        passengers = tg.generate(tick, rng)
        assert len(passengers) == 1
        p = passengers[0]
        
        assert p.source_floor == 0
        assert p.target_floor >= 1
        assert p.direction == 1  # UP


def test_traffic_generator_determinism():
    """Verify that two generators with identically seeded RNGs produce identical sequences."""
    # Seed 1
    rng_a = random.Random(12345)
    tg_a = TrafficGenerator(num_floors=5, arrival_rate=0.4, profile="UNIFORM")
    sequence_a = []
    for tick in range(1, 100):
        p_list = tg_a.generate(tick, rng_a)
        if p_list:
            sequence_a.append((p_list[0].source_floor, p_list[0].target_floor))
            
    # Seed 2 (identical)
    rng_b = random.Random(12345)
    tg_b = TrafficGenerator(num_floors=5, arrival_rate=0.4, profile="UNIFORM")
    sequence_b = []
    for tick in range(1, 100):
        p_list = tg_b.generate(tick, rng_b)
        if p_list:
            sequence_b.append((p_list[0].source_floor, p_list[0].target_floor))
            
    assert sequence_a == sequence_b
    assert len(sequence_a) > 0  # Verify some passenger spawns actually happened

// src/elevatorsim/web/frontend/src/utils/simulationHelper.js

/**
 * Reconstruct simulation state at a specific tick (supports multi-car)
 */
export function reconstructState(events, tick, numCars = 1) {
  const state = {
    cars: {},  // keyed by car_id (e.g. "C1", "C2")
    floorQueues: {},
    logs: [],
    rawEvents: []
  };

  // Initialize cars
  for (let c = 1; c <= numCars; c++) {
    state.cars[`C${c}`] = {
      floor: 0,
      targetFloor: null,
      doorState: "CLOSED",
      onboardPassengers: []
    };
  }

  // Initialize floor queues
  for (let i = 0; i < 10; i++) {
    state.floorQueues[i] = [];
  }

  if (!events || events.length === 0) return state;

  // Character weights, mirroring the backend table (passenger.py); used as a
  // fallback for cached runs recorded before weights existed
  const CHARACTER_WEIGHTS_KG = [30, 32, 38, 60, 75, 52, 68, 62, 80, 58, 65, 90];
  const fallbackWeight = (id) => {
    const n = parseInt(String(id).replace(/\D/g, ''), 10);
    return CHARACTER_WEIGHTS_KG[(Number.isNaN(n) ? 0 : n) % CHARACTER_WEIGHTS_KG.length];
  };

  // Gather passenger targets and weights on spawn
  const passengerTargets = {};
  const passengerWeights = {};
  for (const ev of events) {
    if (ev.event_type === "PassengerSpawned") {
      passengerTargets[ev.passenger_id] = ev.target;
      passengerWeights[ev.passenger_id] = ev.weight_kg ?? fallbackWeight(ev.passenger_id);
    }
  }

  // Process events up to current tick
  for (const ev of events) {
    if (ev.time > tick) break;

    state.rawEvents.push(ev);
    state.logs.push(ev.message);

    // Resolve which car this event applies to; fall back to "C1" for legacy single-car events
    const carId = ev.car_id || 'C1';

    switch (ev.event_type) {
      case "PassengerSpawned": {
        const { passenger_id, source, target } = ev;
        state.floorQueues[source].push({ id: passenger_id, target, weight: passengerWeights[passenger_id] });
        break;
      }
      case "PassengerBoarded": {
        const { passenger_id, floor } = ev;
        state.floorQueues[floor] = state.floorQueues[floor].filter(p => p.id !== passenger_id);
        if (state.cars[carId]) {
          state.cars[carId].onboardPassengers.push({
            id: passenger_id,
            target: passengerTargets[passenger_id] || 0,
            weight: passengerWeights[passenger_id],
          });
        }
        break;
      }
      case "PassengerDeboarded": {
        const { passenger_id } = ev;
        if (state.cars[carId]) {
          state.cars[carId].onboardPassengers = state.cars[carId].onboardPassengers.filter(p => p.id !== passenger_id);
        }
        break;
      }
      case "CarMoved": {
        if (state.cars[carId]) {
          state.cars[carId].floor = ev.to_floor;
        }
        break;
      }
      case "CarArrived": {
        if (state.cars[carId]) {
          state.cars[carId].floor = ev.floor;
        }
        break;
      }
      case "DoorOpened": {
        if (state.cars[carId]) {
          state.cars[carId].doorState = "OPEN";
        }
        break;
      }
      case "DoorClosed": {
        if (state.cars[carId]) {
          state.cars[carId].doorState = "CLOSED";
        }
        break;
      }
      case "BoardingRefused": {
        if (state.cars[carId]) {
          // Flag stays on briefly so the FULL badge shows at the dramatic moment
          state.cars[carId].refusedRecently = (tick - ev.time) <= 2;
        }
        break;
      }
      default:
        break;
    }
  }

  return state;
}

/**
 * Calculate the average wait time of all active and completed passengers at tick t
 */
export function getAverageWaitTimeAtTick(events, tick) {
  const spawnTimes = {};
  const boardTimes = {};

  for (const ev of events) {
    if (ev.time > tick) break;
    if (ev.event_type === "PassengerSpawned") {
      spawnTimes[ev.passenger_id] = ev.time;
    } else if (ev.event_type === "PassengerBoarded") {
      boardTimes[ev.passenger_id] = ev.time;
    }
  }

  const passengers = Object.keys(spawnTimes);
  if (passengers.length === 0) return 0;

  let totalWait = 0;
  for (const pid of passengers) {
    const spawn = spawnTimes[pid];
    const board = boardTimes[pid];
    if (board !== undefined) {
      totalWait += (board - spawn);
    } else {
      totalWait += (tick - spawn);
    }
  }
  return parseFloat((totalWait / passengers.length).toFixed(1));
}

/**
 * Calculate total energy consumption of all cars up to tick t
 */
export function getEnergyAtTick(events, tick) {
  if (!events || !events.events) return 0;
  let energy = 0;
  const carWasMoving = {};

  for (const ev of events.events) {
    if (ev.time > tick) break;
    const carId = ev.car_id || 'C1';

    if (ev.event_type === "CarMoved") {
      const distance = Math.abs(ev.to_floor - ev.from_floor);
      energy += distance * 1.0;
      if (!carWasMoving[carId]) {
        energy += 5.0; // Motor start
      }
      carWasMoving[carId] = true;
    } else if (ev.event_type === "DoorOpened") {
      energy += 0.5; // Door cycle
      carWasMoving[carId] = false;
    }
  }
  return parseFloat(energy.toFixed(1));
}


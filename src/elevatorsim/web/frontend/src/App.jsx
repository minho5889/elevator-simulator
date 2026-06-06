// src/elevatorsim/web/frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, RotateCcw, ChevronRight, Settings, 
  Key, AlertCircle, HelpCircle, Activity, Award, Navigation, UserCheck, Clock
} from 'lucide-react';

const BACKEND_URL = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

// Reconstruct simulation state at a specific tick
function reconstructState(events, tick) {
  const state = {
    carFloor: 0,
    targetFloor: null,
    doorState: "CLOSED",
    onboardPassengers: [],
    floorQueues: {},
    logs: [],
    rawEvents: []
  };

  // Initialize floor queues
  for (let i = 0; i < 10; i++) {
    state.floorQueues[i] = [];
  }

  if (!events || events.length === 0) return state;

  // Gather passenger targets on spawn
  const passengerTargets = {};
  for (const ev of events) {
    if (ev.event_type === "PassengerSpawned") {
      passengerTargets[ev.passenger_id] = ev.target;
    }
  }

  // Process events up to current tick
  for (const ev of events) {
    if (ev.time > tick) break;

    state.rawEvents.push(ev);
    state.logs.push(ev.message);

    switch (ev.event_type) {
      case "PassengerSpawned": {
        const { passenger_id, source, target } = ev;
        state.floorQueues[source].push({ id: passenger_id, target });
        break;
      }
      case "PassengerBoarded": {
        const { passenger_id, floor } = ev;
        state.floorQueues[floor] = state.floorQueues[floor].filter(p => p.id !== passenger_id);
        state.onboardPassengers.push({ id: passenger_id, target: passengerTargets[passenger_id] || 0 });
        break;
      }
      case "PassengerDeboarded": {
        const { passenger_id } = ev;
        state.onboardPassengers = state.onboardPassengers.filter(p => p.id !== passenger_id);
        break;
      }
      case "CarMoved": {
        state.carFloor = ev.to_floor;
        break;
      }
      case "CarArrived": {
        state.carFloor = ev.floor;
        break;
      }
      case "DoorOpened": {
        state.doorState = "OPEN";
        break;
      }
      case "DoorClosed": {
        state.doorState = "CLOSED";
        break;
      }
      default:
        break;
    }
  }

  // Infer active target floor (find the next CarArrived after latest CarMoved)
  let targetFloor = null;
  const lastMove = events.find(ev => ev.time <= tick && ev.event_type === "CarMoved");
  if (lastMove) {
    const nextArrival = events.find(ev => ev.time >= lastMove.time && ev.event_type === "CarArrived");
    if (nextArrival) {
      targetFloor = nextArrival.floor;
    }
  }
  state.targetFloor = targetFloor;

  return state;
}

// Calculate the average wait time of all active and completed passengers at tick t
function getAverageWaitTimeAtTick(events, tick) {
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

export default function App() {
  // App Configurations & Key
  const [userApiKey, setUserApiKey] = useState(() => localStorage.getItem('gemini_api_key') || '');
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [keyChecking, setKeyChecking] = useState(false);
  const [keyCheckResult, setKeyCheckResult] = useState(null);

  // Preset scenarios database
  const [presets, setPresets] = useState({});
  const [activePreset, setActivePreset] = useState('quiet_day');

  // Custom simulation configs
  const [seed, setSeed] = useState(42);
  const [floors, setFloors] = useState(5);
  const [arrivalRate, setArrivalRate] = useState(0.2);
  const [maxTicks, setMaxTicks] = useState(50);
  const [profile, setProfile] = useState('UNIFORM');
  
  // App status states
  const [simulating, setSimulating] = useState(false);
  const [simError, setSimError] = useState(null);

  // Main Simulation Event Data
  const [heuristicData, setHeuristicData] = useState(null);
  const [agenticData, setAgenticData] = useState(null);
  const [agenticError, setAgenticError] = useState(null);

  // Playback Control States
  const [currentTick, setCurrentTick] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(500); // ms per tick

  // Scroll references for logs console
  const hLogRef = useRef(null);
  const aLogRef = useRef(null);

  // Fetch presets on load
  useEffect(() => {
    fetch(`${BACKEND_URL}/api/presets`)
      .then(res => res.json())
      .then(data => {
        setPresets(data);
        if (data.quiet_day) {
          loadPresetData('quiet_day', data.quiet_day);
        }
      })
      .catch(err => {
        console.error('Failed to load presets:', err);
      });
  }, []);

  // Playback Interval Control
  useEffect(() => {
    let interval = null;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentTick(prev => {
          if (prev >= maxTicks) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, playbackSpeed);
    } else {
      clearInterval(interval);
    }
    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, maxTicks]);

  // Autoscroll consoles when tick changes
  useEffect(() => {
    if (hLogRef.current) hLogRef.current.scrollTop = hLogRef.current.scrollHeight;
    if (aLogRef.current) aLogRef.current.scrollTop = aLogRef.current.scrollHeight;
  }, [currentTick]);

  const loadPresetData = (presetName, presetObj) => {
    setActivePreset(presetName);
    setSeed(presetObj.seed);
    setFloors(presetObj.heuristic.metrics.total_ticks ? 5 : 5); // Default to 5 floors
    setArrivalRate(presetObj.arrival_rate);
    setMaxTicks(presetObj.max_ticks);
    setProfile(presetObj.profile);
    
    setHeuristicData(presetObj.heuristic);
    setAgenticData(presetObj.agentic);
    setAgenticError(null);
    setCurrentTick(0);
    setIsPlaying(false);
  };

  const handlePresetChange = (presetName) => {
    if (presets[presetName]) {
      loadPresetData(presetName, presets[presetName]);
    }
  };

  const handleTestKey = () => {
    if (!userApiKey.trim()) {
      setKeyCheckResult({ success: false, message: 'Please enter a key.' });
      return;
    }
    setKeyChecking(true);
    setKeyCheckResult(null);

    fetch(`${BACKEND_URL}/api/test-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: userApiKey })
    })
      .then(res => res.json())
      .then(data => {
        setKeyChecking(false);
        setKeyCheckResult(data);
        if (data.success) {
          localStorage.setItem('gemini_api_key', userApiKey);
        }
      })
      .catch(err => {
        setKeyChecking(false);
        setKeyCheckResult({ success: false, message: `Server error: ${err.message}` });
      });
  };

  const handleSaveSettings = () => {
    localStorage.setItem('gemini_api_key', userApiKey);
    setShowSettingsModal(false);
    setKeyCheckResult(null);
  };

  const runCustomSimulation = () => {
    setSimulating(true);
    setSimError(null);
    setIsPlaying(false);
    setCurrentTick(0);

    fetch(`${BACKEND_URL}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seed: Number(seed),
        num_floors: Number(floors),
        arrival_rate: Number(arrivalRate),
        profile: profile,
        max_ticks: Number(maxTicks),
        api_key: userApiKey || null,
        run_agentic: true
      })
    })
      .then(res => {
        if (!res.ok) throw new Error('API server returned error.');
        return res.json();
      })
      .then(data => {
        setSimulating(false);
        setActivePreset('custom');
        setHeuristicData(data.heuristic);
        setAgenticData(data.agentic);
        setAgenticError(data.agentic_error);
      })
      .catch(err => {
        setSimulating(false);
        setSimError(err.message);
        console.error('Simulation error:', err);
      });
  };

  // Reconstruct States
  const hState = reconstructState(heuristicData?.events, currentTick);
  const aState = reconstructState(agenticData?.events, currentTick);

  // Reconstruct Metrics
  const hMetricsAtTick = heuristicData?.metrics;
  const aMetricsAtTick = agenticData?.metrics;

  // Chart Coordinates calculation
  const getChartPoints = (eventsData) => {
    if (!eventsData || !eventsData.events) return "";
    const points = [];
    for (let t = 0; t <= maxTicks; t++) {
      const waitTime = getAverageWaitTimeAtTick(eventsData.events, t);
      points.push({ x: t, y: waitTime });
    }
    return points;
  };

  const hChartPoints = getChartPoints(heuristicData);
  const aChartPoints = getChartPoints(agenticData);

  // Find max wait time across both curves to scale Y axis
  const maxWaitVal = Math.max(
    ...hChartPoints.map(p => p.y),
    ...aChartPoints.map(p => p.y),
    5 // Min Y scaling is 5 ticks
  );

  const renderSVGChart = () => {
    const width = 600;
    const height = 120;
    const padding = 15;

    const scaleX = (val) => padding + (val / maxTicks) * (width - 2 * padding);
    const scaleY = (val) => height - padding - (val / maxWaitVal) * (height - 2 * padding);

    const generateSVGPath = (points) => {
      if (points.length === 0) return "";
      return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(p.x)} ${scaleY(p.y)}`).join(' ');
    };

    const hPath = generateSVGPath(hChartPoints);
    const aPath = generateSVGPath(aChartPoints);

    return (
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="mt-4">
        {/* Grid lines */}
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border-color)" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="var(--border-color)" />
        
        {/* LOOK Heuristic Path */}
        {hPath && (
          <path d={hPath} fill="none" stroke="var(--look-cyan)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}
        
        {/* Gemini Agent Path */}
        {aPath && (
          <path d={aPath} fill="none" stroke="var(--agent-violet)" strokeWidth="2" strokeDasharray="3 3" strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* Playhead vertical line */}
        <line 
          x1={scaleX(currentTick)} 
          y1={padding} 
          x2={scaleX(currentTick)} 
          y2={height - padding} 
          stroke="#f8fafc" 
          strokeWidth="1.5" 
          strokeDasharray="2 2"
        />
        <circle cx={scaleX(currentTick)} cy={scaleY(getAverageWaitTimeAtTick(heuristicData?.events || [], currentTick))} r="4" fill="var(--look-cyan)" />
        {agenticData && (
          <circle cx={scaleX(currentTick)} cy={scaleY(getAverageWaitTimeAtTick(agenticData?.events || [], currentTick))} r="4" fill="var(--agent-violet)" />
        )}
      </svg>
    );
  };

  return (
    <div className="container slide-up">
      {/* Header */}
      <header className="flex justify-between items-center mb-6 pb-4 border-b border-[var(--border-color)]">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--text-primary)] m-0 flex items-center gap-2">
            <Activity className="text-cyan-500 w-8 h-8" />
            Elevator Simulator
            <span className="text-xs bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 rounded-full font-normal">A/B Testing Dashboard</span>
          </h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">Comparing LOOK Heuristic vs. Gemini-3.5-Flash Strands Agent</p>
        </div>
        <button 
          onClick={() => setShowSettingsModal(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border-color)] bg-slate-900 text-slate-300 hover:text-white hover:border-slate-600 transition"
        >
          <Settings className="w-4 h-4" />
          Settings
        </button>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column - Configuration (3 cols) */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          
          {/* Preset scenarios */}
          <div className="glass-panel p-4 flex flex-col gap-3">
            <h2 className="text-sm uppercase tracking-wider text-[var(--text-muted)] font-bold m-0">Presets</h2>
            <div className="flex flex-col gap-2">
              <button 
                onClick={() => handlePresetChange('quiet_day')}
                className={`text-left px-3 py-2 rounded-lg text-sm font-medium transition ${activePreset === 'quiet_day' ? 'bg-cyan-500/15 border border-cyan-500/40 text-cyan-400' : 'bg-slate-900 border border-transparent text-slate-400 hover:bg-slate-800'}`}
              >
                Uniform Quiet Day
              </button>
              <button 
                onClick={() => handlePresetChange('morning_rush')}
                className={`text-left px-3 py-2 rounded-lg text-sm font-medium transition ${activePreset === 'morning_rush' ? 'bg-cyan-500/15 border border-cyan-500/40 text-cyan-400' : 'bg-slate-900 border border-transparent text-slate-400 hover:bg-slate-800'}`}
              >
                Morning Lobby Rush
              </button>
              <button 
                onClick={() => handlePresetChange('evening_rush')}
                className={`text-left px-3 py-2 rounded-lg text-sm font-medium transition ${activePreset === 'evening_rush' ? 'bg-cyan-500/15 border border-cyan-500/40 text-cyan-400' : 'bg-slate-900 border border-transparent text-slate-400 hover:bg-slate-800'}`}
              >
                Evening Departure Rush
              </button>
            </div>
          </div>

          {/* Configuration Parameters */}
          <div className="glass-panel p-4 flex flex-col gap-4">
            <h2 className="text-sm uppercase tracking-wider text-[var(--text-muted)] font-bold m-0">Simulation Config</h2>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--text-secondary)]">Traffic Profile</label>
              <select 
                value={profile} 
                onChange={(e) => setProfile(e.target.value)}
                className="w-full bg-slate-900 border border-[var(--border-color)] rounded-lg px-2.5 py-1.5 text-sm outline-none"
              >
                <option value="UNIFORM">UNIFORM</option>
                <option value="DOWN_PEAK">DOWN_PEAK (Morning)</option>
                <option value="UP_PEAK">UP_PEAK (Evening)</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--text-secondary)] flex justify-between">
                <span>Arrival Probability</span>
                <span className="font-semibold">{arrivalRate}</span>
              </label>
              <input 
                type="range" min="0.1" max="1.0" step="0.05"
                value={arrivalRate} onChange={(e) => setArrivalRate(Number(e.target.value))}
                className="w-full accent-cyan-500"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--text-secondary)] flex justify-between">
                <span>Floors (Shaft Height)</span>
                <span className="font-semibold">{floors}</span>
              </label>
              <input 
                type="range" min="5" max="10" step="1"
                value={floors} onChange={(e) => setFloors(Number(e.target.value))}
                className="w-full accent-cyan-500"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--text-secondary)] flex justify-between">
                <span>Max Ticks</span>
                <span className="font-semibold">{maxTicks}</span>
              </label>
              <input 
                type="range" min="30" max="100" step="10"
                value={maxTicks} onChange={(e) => setMaxTicks(Number(e.target.value))}
                className="w-full accent-cyan-500"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--text-secondary)]">RNG Seed</label>
              <input 
                type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))}
                className="w-full bg-slate-900 border border-[var(--border-color)] rounded-lg px-2.5 py-1.5 text-sm outline-none"
              />
            </div>

            <button 
              onClick={runCustomSimulation}
              disabled={simulating}
              className="w-full mt-2 bg-gradient-to-r from-cyan-500 to-indigo-500 hover:from-cyan-400 hover:to-indigo-400 text-slate-950 font-bold py-2 rounded-lg text-sm transition disabled:opacity-50"
            >
              {simulating ? 'Simulating...' : 'Run Simulation'}
            </button>
            {simError && (
              <p className="text-xs text-red-500 flex items-center gap-1 mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {simError}
              </p>
            )}
          </div>
        </div>

        {/* Center / Right Column - Visualizer & Metrics (9 cols) */}
        <div className="lg:col-span-9 flex flex-col gap-6">

          {/* Playback Control Bar */}
          <div className="glass-panel p-4 flex flex-wrap gap-4 items-center justify-between">
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setIsPlaying(!isPlaying)}
                className="p-2 rounded-full bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition"
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>
              <button 
                onClick={() => { setCurrentTick(0); setIsPlaying(false); }}
                className="p-2 rounded-full border border-[var(--border-color)] bg-slate-900 text-slate-300 hover:text-white hover:border-slate-600 transition"
                title="Reset Simulation"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button 
                onClick={() => { if (currentTick < maxTicks) setCurrentTick(c => c + 1); setIsPlaying(false); }}
                className="p-2 rounded-full border border-[var(--border-color)] bg-slate-900 text-slate-300 hover:text-white hover:border-slate-600 transition"
                title="Manual Tick Step"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Scrubber timeline */}
            <div className="flex-1 min-w-[200px] flex items-center gap-3">
              <span className="text-xs font-semibold font-mono text-cyan-400 w-8">{String(currentTick).padStart(3, '0')}</span>
              <input 
                type="range" min="0" max={maxTicks}
                value={currentTick} onChange={(e) => { setCurrentTick(Number(e.target.value)); setIsPlaying(false); }}
                className="flex-1 accent-cyan-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
              />
              <span className="text-xs font-semibold font-mono text-slate-500 w-8">{String(maxTicks).padStart(3, '0')}</span>
            </div>

            {/* Speed controller */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Speed:</span>
              <select 
                value={playbackSpeed} 
                onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                className="bg-slate-900 border border-[var(--border-color)] rounded-lg px-2 py-1 text-xs outline-none"
              >
                <option value={1000}>0.5x</option>
                <option value={500}>1.0x</option>
                <option value={250}>2.0x</option>
                <option value={100}>5.0x</option>
              </select>
            </div>
          </div>

          {/* Elevator Canvas Shafts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* LOOK Heuristic Shaft */}
            <div className="glass-panel p-4 flex flex-col border-t-2 border-t-[var(--look-cyan)]">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-sm font-semibold tracking-wider text-[var(--look-cyan)] uppercase flex items-center gap-1.5 m-0">
                  <Navigation className="w-4 h-4 rotate-45" />
                  LOOK Heuristic Baseline
                </h3>
                <span className="text-xs bg-slate-900 border border-[var(--border-color)] px-2 py-0.5 rounded-full text-slate-400 font-mono">Offline</span>
              </div>
              
              <ElevatorShaft state={hState} numFloors={floors} accentColor="var(--look-cyan)" />
              <ConsoleTerminal logRef={hLogRef} logs={hState.logs} title="LOOK Event Logs" />
            </div>

            {/* Agentic Gemini Shaft */}
            <div className="glass-panel p-4 flex flex-col border-t-2 border-t-[var(--agent-violet)]">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-sm font-semibold tracking-wider text-[var(--agent-violet)] uppercase flex items-center gap-1.5 m-0">
                  <UserCheck className="w-4 h-4" />
                  Strands + Gemini-3.5-Flash
                </h3>
                <span className="text-xs bg-violet-950/35 border border-violet-800/40 px-2 py-0.5 rounded-full text-violet-400 font-mono">Agentic</span>
              </div>

              {agenticError ? (
                <div className="flex-1 flex flex-col items-center justify-center p-6 text-center bg-slate-950/40 border border-dashed border-[var(--border-color)] rounded-lg min-h-[300px]">
                  <AlertCircle className="w-8 h-8 text-amber-500 mb-2" />
                  <h4 className="text-sm font-bold text-slate-200">Agentic Run Skipped / Failed</h4>
                  <p className="text-xs text-slate-400 mt-1 max-w-[280px] leading-relaxed">
                    {agenticError.includes('RESOURCE_EXHAUSTED') ? 
                      "Gemini API rate limits (RESOURCE_EXHAUSTED 429) hit. Pre-recorded presets bypass this, or you can paste your own key in settings." : 
                      agenticError}
                  </p>
                  <button 
                    onClick={() => setShowSettingsModal(true)}
                    className="mt-3 px-3 py-1.5 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-lg text-xs font-semibold text-slate-300 hover:text-white transition"
                  >
                    Configure Key Settings
                  </button>
                </div>
              ) : (
                <>
                  <ElevatorShaft state={aState} numFloors={floors} accentColor="var(--agent-violet)" />
                  <ConsoleTerminal logRef={aLogRef} logs={aState.logs} title="Agent Event Logs" />
                </>
              )}
            </div>

          </div>

          {/* Telemetry metrics & Line Chart */}
          <div className="glass-panel p-4 flex flex-col gap-4">
            <div className="flex justify-between items-center border-b border-[var(--border-color)] pb-2">
              <h3 className="text-sm uppercase tracking-wider text-[var(--text-muted)] font-bold m-0 flex items-center gap-1">
                <Award className="w-4 h-4 text-amber-500" />
                Performance Comparison
              </h3>
              <span className="text-xs text-slate-400 font-mono">Tick {currentTick} Snapshot</span>
            </div>

            {/* Numerical metrics cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricComparisonCard 
                title="Average Wait Time" 
                hVal={heuristicData ? getAverageWaitTimeAtTick(heuristicData.events, currentTick) : 0}
                aVal={agenticData && !agenticError ? getAverageWaitTimeAtTick(agenticData.events, currentTick) : null}
                unit="ticks"
                icon={<Clock className="w-4 h-4 text-amber-400" />}
              />
              <MetricComparisonCard 
                title="Total Car Moves" 
                hVal={hState.rawEvents.filter(e => e.event_type === "CarMoved").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "CarMoved").length : null}
                unit="moves"
                icon={<Navigation className="w-4 h-4 text-cyan-400" />}
              />
              <MetricComparisonCard 
                title="Completed Passengers" 
                hVal={hState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length : null}
                unit="deboarded"
                icon={<UserCheck className="w-4 h-4 text-emerald-400" />}
              />
              <MetricComparisonCard 
                title="Total Active Spawns" 
                hVal={hState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length : null}
                unit="spawned"
                icon={<Activity className="w-4 h-4 text-purple-400" />}
              />
            </div>

            {/* Line Chart */}
            <div className="flex flex-col gap-2 mt-2 bg-slate-950/40 p-3 rounded-lg border border-[var(--border-color)]">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-slate-300">Live Average Wait Time Profile (LOOK vs Agentic)</span>
                <div className="flex gap-4">
                  <span className="flex items-center gap-1 text-[var(--look-cyan)]">
                    <span className="w-2.5 h-0.5 bg-[var(--look-cyan)] inline-block"></span> LOOK Heuristic
                  </span>
                  <span className="flex items-center gap-1 text-[var(--agent-violet)]">
                    <span className="w-2.5 h-0.5 border-t border-dashed border-[var(--agent-violet)] inline-block"></span> Gemini Agent
                  </span>
                </div>
              </div>
              {renderSVGChart()}
            </div>
          </div>

        </div>

      </div>

      {/* Settings Panel Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
          <div className="glass-panel w-full max-w-md p-6 bg-slate-900 border border-slate-700/60 rounded-xl relative">
            <h2 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
              <Settings className="text-cyan-400 w-5 h-5" />
              Settings & API Keys
            </h2>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-4">
              To configure custom elevator simulations, you can paste your Google AI Studio API key below. 
              The key is saved <strong>locally</strong> in your browser storage and never sent anywhere except the local simulator server.
            </p>

            <div className="flex flex-col gap-2 mb-4">
              <label className="text-xs text-slate-300 font-semibold flex items-center gap-1">
                <Key className="w-3.5 h-3.5" />
                GEMINI_API_KEY
              </label>
              <input 
                type="password" 
                placeholder="AIzaSy..."
                value={userApiKey} 
                onChange={(e) => setUserApiKey(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm outline-none text-white placeholder-slate-600 focus:border-cyan-500"
              />
            </div>

            {keyCheckResult && (
              <div className={`p-3 rounded-lg text-xs mb-4 ${keyCheckResult.success ? 'bg-emerald-950/30 border border-emerald-500/30 text-emerald-400' : 'bg-red-950/30 border border-red-500/30 text-red-400'}`}>
                {keyCheckResult.message}
              </div>
            )}

            <div className="flex gap-3 justify-end mt-6">
              <button 
                onClick={handleTestKey}
                disabled={keyChecking}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 font-semibold rounded-lg text-xs transition disabled:opacity-50"
              >
                {keyChecking ? 'Testing...' : 'Test Connection'}
              </button>
              <button 
                onClick={handleSaveSettings}
                className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-lg text-xs transition"
              >
                Save & Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 py-4 border-t border-[var(--border-color)] text-center text-xs text-[var(--text-muted)] flex justify-between items-center">
        <span>Discrete-Event Elevator Simulator Platform</span>
        <span>Built with Strands & Google Gemini</span>
      </footer>
    </div>
  );
}

// Elevator Shaft Component representing floors, car vertical translation, and queue indicators
function ElevatorShaft({ state, numFloors, accentColor }) {
  // Reconstruct floors (ordered descending so lobby 0 is at bottom)
  const floorIndices = Array.from({ length: numFloors }, (_, i) => numFloors - 1 - i);
  const carFloor = state.carFloor;

  // Calculate vertical percentage offset for absolute positioning of car
  // lobby 0 is bottom, numFloors-1 is top.
  const carBottomPercentage = (carFloor / (numFloors - 1)) * 82; // Bound positioning scale safely

  return (
    <div className="flex-1 flex bg-slate-950/60 border border-[var(--border-color)] rounded-lg p-3 min-h-[360px] relative">
      {/* Floor boundaries and queue details */}
      <div className="flex-1 flex flex-col justify-between">
        {floorIndices.map(fIdx => {
          const isTarget = state.targetFloor === fIdx;
          const waitingQueue = state.floorQueues[fIdx] || [];

          return (
            <div 
              key={fIdx} 
              className="flex justify-between items-center py-2 h-10 border-b border-dashed border-slate-900 last:border-b-0"
            >
              {/* Floor Label */}
              <div className="flex items-center gap-1">
                <span className={`text-xs font-mono font-bold w-5 h-5 flex items-center justify-center rounded ${isTarget ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' : 'bg-slate-900 text-slate-500'}`}>
                  {fIdx}
                </span>
                <span className="text-[10px] text-slate-600 uppercase font-bold tracking-wider">Floor</span>
              </div>

              {/* Waiting Passengers queue indicators */}
              <div className="flex gap-1.5 max-w-[150px] overflow-hidden justify-end">
                {waitingQueue.map(p => (
                  <span 
                    key={p.id} 
                    className="text-[9px] font-mono px-1.5 py-0.5 rounded font-medium bg-slate-900 border border-slate-800 text-slate-400"
                    title={`Passenger ${p.id} heading to floor ${p.target}`}
                  >
                    {p.id}→{p.target}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Vertical Track and moving car graphic */}
      <div className="w-16 flex justify-center border-l border-slate-900 relative">
        <div 
          className="absolute w-12 h-10 rounded-lg flex flex-col justify-center items-center border transition-all duration-300 ease-in-out"
          style={{ 
            bottom: `${carBottomPercentage + 2}%`,
            borderColor: accentColor,
            background: `radial-gradient(ellipse at center, ${accentColor}12 0%, #1e293b 100%)`,
            boxShadow: `0 0 12px 0 ${accentColor}24`
          }}
        >
          {/* Car details: doors and onboard count */}
          <div className="flex w-full justify-between px-1.5 absolute top-1 text-[8px] text-slate-400 font-bold uppercase tracking-wide">
            <span>Car</span>
            <span style={{ color: accentColor }}>C1</span>
          </div>

          {/* Onboard count */}
          <span className="text-xs font-mono font-bold text-white mt-2">
            {state.onboardPassengers.length}
          </span>

          {/* Door state indicators */}
          <div 
            className="w-full flex justify-between absolute bottom-0.5 px-2"
            style={{ animation: state.doorState === 'OPEN' ? 'doorPulse 1.5s infinite' : 'none' }}
          >
            <span className={`w-1 h-2 rounded-sm ${state.doorState === 'OPEN' ? 'bg-emerald-400' : 'bg-slate-700'}`}></span>
            <span className="text-[7px] font-bold text-slate-500 uppercase">{state.doorState}</span>
            <span className={`w-1 h-2 rounded-sm ${state.doorState === 'OPEN' ? 'bg-emerald-400' : 'bg-slate-700'}`}></span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Scrolling event log terminal
function ConsoleTerminal({ logRef, logs, title }) {
  return (
    <div className="mt-4 bg-slate-950 border border-slate-900 rounded-lg p-3 flex flex-col gap-1.5">
      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold border-b border-slate-900 pb-1.5 flex justify-between items-center">
        <span>{title}</span>
        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full pulse-glow"></span>
      </div>
      <div 
        ref={logRef}
        className="h-28 overflow-y-auto text-[10px] font-mono text-slate-400 flex flex-col gap-1.5 scroll-smooth"
      >
        {logs.length === 0 ? (
          <span className="text-slate-700 italic">No events occurred yet. Play or step to start.</span>
        ) : (
          logs.map((log, idx) => {
            // Highlight agent reasoning logs or specific tags
            const isAgentDecision = log.includes('Decided by Gemini');
            const isBoarded = log.includes('BOARDED');
            const isDeboarded = log.includes('DEBOARDED');
            
            let colorClass = 'text-slate-400';
            if (isAgentDecision) colorClass = 'text-purple-400 font-semibold';
            else if (isBoarded) colorClass = 'text-cyan-400';
            else if (isDeboarded) colorClass = 'text-emerald-400';

            return (
              <div key={idx} className={`${colorClass} leading-relaxed`}>
                {log}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// Numerical Telemetry comparisons cards
function MetricComparisonCard({ title, hVal, aVal, unit, icon }) {
  const isBetter = aVal !== null && aVal < hVal; // A lower wait time or moves is usually better
  
  return (
    <div className="bg-slate-950/40 border border-[var(--border-color)] rounded-xl p-3 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] font-medium">
        {icon}
        {title}
      </div>
      <div className="flex items-baseline justify-between mt-1">
        {/* LOOK Heuristic value */}
        <div className="flex flex-col">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">LOOK</span>
          <span className="text-sm font-mono font-bold text-slate-300">{hVal} <span className="text-[10px] font-normal text-slate-500">{unit}</span></span>
        </div>

        {/* Gemini Agent value */}
        <div className="flex flex-col text-right">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Gemini</span>
          {aVal === null ? (
            <span className="text-xs text-slate-600 font-semibold">N/A</span>
          ) : (
            <span className={`text-sm font-mono font-bold ${isBetter ? 'text-emerald-400' : aVal > hVal ? 'text-slate-400' : 'text-slate-300'}`}>
              {aVal} <span className="text-[10px] font-normal text-slate-500">{unit}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

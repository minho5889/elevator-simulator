// src/elevatorsim/web/frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, RotateCcw, ChevronRight, Settings, 
  Key, AlertCircle, HelpCircle, Activity, Award, Navigation, UserCheck, Clock, Zap
} from 'lucide-react';
import { reconstructState, getAverageWaitTimeAtTick, getEnergyAtTick } from './utils/simulationHelper';
import ElevatorShaft from './components/ElevatorShaft';
import ConsoleTerminal from './components/ConsoleTerminal';
import MetricComparisonCard from './components/MetricComparisonCard';
import WaitTimeChart from './components/WaitTimeChart';
import SettingsModal from './components/SettingsModal';
import PassengerSpawnModal from './components/PassengerSpawnModal';

const BACKEND_URL = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';


export default function App() {
  // App Configurations & Key
  const [userApiKey, setUserApiKey] = useState(() => localStorage.getItem('gemini_api_key') || '');
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [keyChecking, setKeyChecking] = useState(false);
  const [keyCheckResult, setKeyCheckResult] = useState(null);
  const [llmProvider, setLlmProvider] = useState(() => localStorage.getItem('llm_provider') || 'gemini');
  const [ollamaHost, setOllamaHost] = useState(() => localStorage.getItem('ollama_host') || 'http://localhost:11434');
  const [ollamaModelId, setOllamaModelId] = useState(() => localStorage.getItem('ollama_model_id') || 'gemma4:e4b');

  // Preset scenarios database
  const [presets, setPresets] = useState({});
  const [activePreset, setActivePreset] = useState('quiet_day');

  // Custom simulation configs
  const [seed, setSeed] = useState(42);
  const [floors, setFloors] = useState(5);
  const [arrivalRate, setArrivalRate] = useState(0.2);
  const [maxTicks, setMaxTicks] = useState(50);
  const [numCars, setNumCars] = useState(1);
  const [carSpeeds, setCarSpeeds] = useState([1.0]);

  // Expand/truncate carSpeeds array dynamically as numCars changes
  useEffect(() => {
    setCarSpeeds(prev => {
      if (prev.length === numCars) return prev;
      if (prev.length < numCars) {
        const added = Array(numCars - prev.length).fill(1.0);
        return [...prev, ...added];
      } else {
        return prev.slice(0, numCars);
      }
    });
  }, [numCars]);
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

  // Live Interactive Mode States
  const [isInteractiveMode, setIsInteractiveMode] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [activeSpawnFloor, setActiveSpawnFloor] = useState(null);

  const wsRef = useRef(null);
  const playbackTimeoutRef = useRef(null);
  const intervalRef = useRef(null);

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

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (playbackTimeoutRef.current) clearTimeout(playbackTimeoutRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Sync references to avoid stale closures in WebSocket handlers
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => {
    isPlayingRef.current = isPlaying;

    if (isPlaying) {
      if (isInteractiveMode) {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'step' }));
        }
      } else {
        intervalRef.current = setInterval(() => {
          setCurrentTick(prev => {
            if (prev >= maxTicks) {
              setIsPlaying(false);
              return prev;
            }
            return prev + 1;
          });
        }, playbackSpeed);
      }
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (playbackTimeoutRef.current) {
        clearTimeout(playbackTimeoutRef.current);
        playbackTimeoutRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (playbackTimeoutRef.current) clearTimeout(playbackTimeoutRef.current);
    };
  }, [isPlaying, isInteractiveMode, maxTicks, playbackSpeed]);

  const playbackSpeedRef = useRef(playbackSpeed);
  useEffect(() => {
    playbackSpeedRef.current = playbackSpeed;
  }, [playbackSpeed]);

  // Autoscroll consoles when tick changes
  useEffect(() => {
    if (hLogRef.current) hLogRef.current.scrollTop = hLogRef.current.scrollHeight;
    if (aLogRef.current) aLogRef.current.scrollTop = aLogRef.current.scrollHeight;
  }, [currentTick]);

  const initWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (playbackTimeoutRef.current) {
      clearTimeout(playbackTimeoutRef.current);
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
    const wsUrl = `${wsProtocol}//${wsHost}/api/ws/simulate`;

    console.log('Connecting to WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connection opened.');
      setWsConnected(true);
      
      // Initialize on backend
      ws.send(JSON.stringify({
        type: 'init',
        config: {
          seed: Number(seed),
          num_floors: Number(floors),
          num_cars: Number(numCars),
          car_speeds: carSpeeds,
          arrival_rate: Number(arrivalRate),
          profile: profile,
          max_ticks: Number(maxTicks),
          api_key: userApiKey || null,
          run_agentic: true,
          llm_provider: llmProvider,
          ollama_host: ollamaHost,
          ollama_model_id: ollamaModelId
        }
      }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === 'state') {
        setIsAgentThinking(false);
        const { current_tick, heuristic_events, agentic_events, agentic_error } = msg;

        setHeuristicData(prev => {
          const existingEvents = (current_tick === 0 || !prev) ? [] : (prev.events || []);
          return {
            events: [...existingEvents, ...heuristic_events]
          };
        });

        setAgenticData(prev => {
          const existingEvents = (current_tick === 0 || !prev) ? [] : (prev.events || []);
          return {
            events: [...existingEvents, ...agentic_events]
          };
        });

        setAgenticError(agentic_error);
        setCurrentTick(current_tick);

        // Pull stepping loop: trigger next step after tick delay if playing
        if (isPlayingRef.current && current_tick < maxTicks) {
          playbackTimeoutRef.current = setTimeout(() => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: 'step' }));
            }
          }, playbackSpeedRef.current);
        } else if (current_tick >= maxTicks) {
          setIsPlaying(false);
        }
      } else if (msg.type === 'thinking') {
        setIsAgentThinking(true);
      } else if (msg.type === 'error') {
        setIsAgentThinking(false);
        setIsPlaying(false);
        setSimError(msg.message);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed.');
      setWsConnected(false);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setSimError('WebSocket connection error.');
    };
  };

  const loadPresetData = (presetName, presetObj) => {
    setActivePreset(presetName);
    setSeed(presetObj.seed);
    setFloors(presetObj.num_floors || 5);
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
      setIsInteractiveMode(false);
      setIsPlaying(false);
      setIsAgentThinking(false);
      if (wsRef.current) {
        wsRef.current.close();
      }
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
    localStorage.setItem('llm_provider', llmProvider);
    localStorage.setItem('ollama_host', ollamaHost);
    localStorage.setItem('ollama_model_id', ollamaModelId);
    setShowSettingsModal(false);
    setKeyCheckResult(null);

    // If mid-simulation, send config update to WebSocket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'config',
        api_key: userApiKey || null,
        llm_provider: llmProvider,
        ollama_host: ollamaHost,
        ollama_model_id: ollamaModelId
      }));
    }
  };

  const runCustomSimulation = () => {
    setSimError(null);
    setIsPlaying(false);
    setCurrentTick(0);
    setIsInteractiveMode(true);
    setActivePreset('custom');

    // Instantiate interactive WebSocket session
    initWebSocket();
  };

  const spawnPassenger = (source, target) => {
    if (!isInteractiveMode) {
      alert("Manual passenger spawning is only supported in custom interactive simulations. Please click 'Run Simulation' to start one first.");
      return;
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'spawn',
        source: Number(source),
        target: Number(target)
      }));
    } else {
      setSimError("WebSocket is not connected. Cannot spawn passenger.");
    }
    setActiveSpawnFloor(null);
  };

  const handleRandomSpawn = () => {
    if (!isInteractiveMode) {
      alert("Manual passenger spawning is only supported in custom interactive simulations. Please click 'Run Simulation' to start one first.");
      return;
    }

    const source = Math.floor(Math.random() * floors);
    let target = Math.floor(Math.random() * floors);
    while (target === source) {
      target = Math.floor(Math.random() * floors);
    }

    spawnPassenger(source, target);
  };

  // Reconstruct States
  const hState = reconstructState(heuristicData?.events, currentTick, numCars);
  const aState = reconstructState(agenticData?.events, currentTick, numCars);

  // Reconstruct Metrics
  const hMetricsAtTick = heuristicData?.metrics;
  const aMetricsAtTick = agenticData?.metrics;

  // Chart Coordinates calculation
  const getChartPoints = (eventsData) => {
    if (!eventsData || !eventsData.events) return [];
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

  // Merge both wait-time curves into a single Recharts-friendly series
  const chartData = hChartPoints.map((p, i) => ({
    tick: p.x,
    look: p.y,
    gemini: aChartPoints[i] ? aChartPoints[i].y : null,
  }));
  const hasAgenticSeries = !!agenticData && !agenticError;


  return (
    <div className="container slide-up">
      {/* Header */}
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 mb-6 pb-5 border-b border-[var(--line)]">
        <div>
          <h1 className="display text-2xl sm:text-3xl text-[var(--ink)] m-0 flex flex-wrap items-baseline gap-3">
            <span>Elevator simulator</span>
            <span className="[font-family:var(--sans)] text-xs bg-[var(--well)] text-[var(--ink-2)] border border-[var(--line)] px-2.5 py-0.5 rounded-full">A/B dashboard</span>
          </h1>
          <p className="text-xs sm:text-sm text-[var(--ink-2)] mt-1.5">LOOK heuristic vs Gemini agent, side by side</p>
        </div>
        <button
          onClick={() => setShowSettingsModal(true)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--line)] bg-transparent text-sm text-[var(--ink-2)] hover:text-[var(--ink)] hover:bg-[var(--well)] transition self-stretch sm:self-auto justify-center"
        >
          <Settings className="w-4 h-4" />
          Settings
        </button>
      </header>

      {/* Main Grid */}
      <div role="main" className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column - Configuration (3 cols) */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          
          {/* Preset scenarios */}
          <div className="panel p-4 flex flex-col gap-3">
            <h2 className="text-xs font-medium text-[var(--ink-3)] m-0">Presets</h2>
            <div className="flex flex-col gap-1">
              <button
                onClick={() => handlePresetChange('quiet_day')}
                className={`text-left px-3 py-2 rounded-lg text-sm transition ${activePreset === 'quiet_day' ? 'bg-[var(--well)] border border-[var(--line)] text-[var(--ink)] font-medium' : 'bg-transparent border border-transparent text-[var(--ink-2)] hover:bg-[var(--well)]'}`}
              >
                Uniform quiet day
              </button>
              <button
                onClick={() => handlePresetChange('morning_rush')}
                className={`text-left px-3 py-2 rounded-lg text-sm transition ${activePreset === 'morning_rush' ? 'bg-[var(--well)] border border-[var(--line)] text-[var(--ink)] font-medium' : 'bg-transparent border border-transparent text-[var(--ink-2)] hover:bg-[var(--well)]'}`}
              >
                Morning lobby rush
              </button>
              <button
                onClick={() => handlePresetChange('evening_rush')}
                className={`text-left px-3 py-2 rounded-lg text-sm transition ${activePreset === 'evening_rush' ? 'bg-[var(--well)] border border-[var(--line)] text-[var(--ink)] font-medium' : 'bg-transparent border border-transparent text-[var(--ink-2)] hover:bg-[var(--well)]'}`}
              >
                Evening departure rush
              </button>
            </div>
          </div>

          {/* Configuration Parameters */}
          <div className="panel p-4 flex flex-col gap-4">
            <h2 className="text-xs font-medium text-[var(--ink-3)] m-0">Simulation config</h2>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)]">Traffic profile</label>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                aria-label="Traffic profile"
                className="w-full bg-[var(--well)] border border-[var(--line)] rounded-lg px-2.5 py-1.5 text-sm outline-none text-[var(--ink)]"
              >
                <option value="UNIFORM">Uniform</option>
                <option value="DOWN_PEAK">Down-peak (morning)</option>
                <option value="UP_PEAK">Up-peak (evening)</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)] flex justify-between">
                <span>Arrival probability</span>
                <span className="font-medium font-mono text-[var(--ink)]">{arrivalRate}</span>
              </label>
              <input
                type="range" min="0.1" max="1.0" step="0.05" aria-label="Arrival probability"
                value={arrivalRate} onChange={(e) => setArrivalRate(Number(e.target.value))}
                className="w-full accent-[#2A2723]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)] flex justify-between">
                <span>Floors</span>
                <span className="font-medium font-mono text-[var(--ink)]">{floors}</span>
              </label>
              <input
                type="range" min="5" max="10" step="1" aria-label="Number of floors"
                value={floors} onChange={(e) => setFloors(Number(e.target.value))}
                className="w-full accent-[#2A2723]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)] flex justify-between">
                <span>Elevator cars</span>
                <span className="font-medium font-mono text-[var(--ink)]">{numCars}</span>
              </label>
              <input
                type="range" min="1" max="6" step="1" aria-label="Number of elevator cars"
                value={numCars} onChange={(e) => setNumCars(Number(e.target.value))}
                className="w-full accent-[#2A2723]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)] flex justify-between">
                <span>Max ticks</span>
                <span className="font-medium font-mono text-[var(--ink)]">{maxTicks}</span>
              </label>
              <input
                type="range" min="30" max="100" step="10" aria-label="Maximum ticks"
                value={maxTicks} onChange={(e) => setMaxTicks(Number(e.target.value))}
                className="w-full accent-[#2A2723]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-[var(--ink-2)]">RNG seed</label>
              <input
                type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} aria-label="RNG seed"
                className="w-full bg-[var(--well)] border border-[var(--line)] rounded-lg px-2.5 py-1.5 text-sm outline-none text-[var(--ink)] font-mono"
              />
            </div>

            <button
              onClick={runCustomSimulation}
              disabled={simulating}
              className="w-full mt-2 bg-[var(--ink)] hover:bg-[#3C3833] text-[var(--paper)] font-medium py-2 rounded-lg text-sm transition disabled:opacity-50"
            >
              {simulating ? 'Simulating…' : 'Run simulation'}
            </button>
            {simError && (
              <p className="text-xs text-[var(--error-text)] flex items-center gap-1 mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {simError}
              </p>
            )}
          </div>
        </div>

        {/* Center / Right Column - Visualizer & Metrics (9 cols) */}
        <div className="lg:col-span-9 flex flex-col gap-6">

          {/* Playback Control Bar */}
          <div className="panel p-4 flex flex-wrap gap-4 items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                aria-label={isPlaying ? 'Pause playback' : 'Play playback'}
                className="p-2 rounded-full bg-[var(--ink)] hover:bg-[#3C3833] text-[var(--paper)] transition"
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>
              <button 
                onClick={() => {
                  setCurrentTick(0);
                  setIsPlaying(false);
                  setIsAgentThinking(false);
                  if (playbackTimeoutRef.current) {
                    clearTimeout(playbackTimeoutRef.current);
                    playbackTimeoutRef.current = null;
                  }
                  if (intervalRef.current) {
                    clearInterval(intervalRef.current);
                    intervalRef.current = null;
                  }
                  if (isInteractiveMode) {
                    initWebSocket();
                  }
                }}
                className="p-2 rounded-full border border-[var(--line)] bg-transparent text-[var(--ink-2)] hover:text-[var(--ink)] hover:bg-[var(--well)] transition"
                title="Reset simulation"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button 
                onClick={() => {
                  setIsPlaying(false);
                  if (isInteractiveMode) {
                    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                      wsRef.current.send(JSON.stringify({ type: 'step' }));
                    }
                  } else {
                    if (currentTick < maxTicks) {
                      setCurrentTick(c => c + 1);
                    }
                  }
                }}
                className="p-2 rounded-full border border-[var(--line)] bg-transparent text-[var(--ink-2)] hover:text-[var(--ink)] hover:bg-[var(--well)] transition"
                title="Step one tick"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Scrubber timeline */}
            <div className="flex-1 min-w-[200px] flex items-center gap-3">
              <span className="text-xs font-medium font-mono text-[var(--ink)] w-8">{String(currentTick).padStart(3, '0')}</span>
              <input
                type="range" min="0" max={maxTicks} aria-label="Timeline scrubber"
                value={currentTick} onChange={(e) => { setCurrentTick(Number(e.target.value)); setIsPlaying(false); }}
                disabled={isInteractiveMode}
                className="flex-1 accent-[#2A2723] h-1.5 cursor-pointer disabled:opacity-50"
              />
              <span className="text-xs font-mono text-[var(--ink-3)] w-8">{String(maxTicks).padStart(3, '0')}</span>
            </div>

            {/* Speed controller */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--ink-3)]">Speed</span>
              <select
                value={playbackSpeed}
                onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                aria-label="Playback speed"
                className="bg-[var(--well)] border border-[var(--line)] rounded-lg px-2 py-1 text-xs outline-none text-[var(--ink)]"
              >
                <option value={1000}>0.5x</option>
                <option value={500}>1.0x</option>
                <option value={250}>2.0x</option>
                <option value={100}>5.0x</option>
              </select>
            </div>
          </div>

          {/* Interactive Spawning Helper Banner */}
          {isInteractiveMode && (
            <div className="px-4 py-2 flex justify-between items-center bg-[var(--look-fill)] border border-[var(--look)] rounded-lg text-xs slide-up">
              <span className="flex items-center gap-2 text-[var(--look-text)] font-medium">
                <span className="w-2 h-2 rounded-full bg-[var(--look)] pulse-glow"></span>
                Interactive mode — click any floor row to spawn passengers.
              </span>
              <button
                onClick={handleRandomSpawn}
                className="px-2.5 py-1 bg-[var(--surface)] hover:bg-white border border-[var(--look)] text-[var(--look-text)] font-medium rounded-md text-[11px] transition"
              >
                Spawn random passenger
              </button>
            </div>
          )}

          {/* Elevator Canvas Shafts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* LOOK Heuristic Shaft */}
            <div className="panel p-4 flex flex-col border-t-2 border-t-[var(--look)] rounded-t-none">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-sm font-medium text-[var(--look-text)] flex items-center gap-1.5 m-0">
                  <Navigation className="w-3.5 h-3.5 rotate-45" />
                  LOOK heuristic
                </h3>
                <span className="text-[11px] bg-[var(--well)] border border-[var(--line)] px-2 py-0.5 rounded-full text-[var(--ink-3)]">offline</span>
              </div>

              <ElevatorShaft
                state={hState}
                numFloors={floors}
                numCars={numCars}
                accent="look"
                onFloorClick={isInteractiveMode ? (fIdx) => setActiveSpawnFloor(fIdx) : null}
              />
              <ConsoleTerminal logRef={hLogRef} logs={hState.logs} title="LOOK event log" />
            </div>

            {/* Agentic Gemini Shaft */}
            <div className={`panel p-4 flex flex-col border-t-2 border-t-[var(--agent)] rounded-t-none relative transition-all duration-300 ${isAgentThinking ? 'border-[var(--agent)]' : ''}`}>
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-sm font-medium text-[var(--agent-text)] flex items-center gap-1.5 m-0">
                  <UserCheck className="w-3.5 h-3.5" />
                  Gemini agent
                </h3>
                <span className="text-[11px] bg-[var(--agent-fill)] border border-[var(--agent)] px-2 py-0.5 rounded-full text-[var(--agent-text)]">agentic</span>
              </div>

              {isAgentThinking && (
                <div className="absolute inset-0 bg-[rgba(250,249,245,0.88)] rounded-lg z-10 flex flex-col items-center justify-center text-center p-6">
                  <div className="w-8 h-8 rounded-full border-2 border-t-[var(--agent)] border-r-transparent animate-spin mb-3"></div>
                  <h4 className="text-sm font-medium text-[var(--ink)]">Gemini is thinking…</h4>
                  <p className="text-[11px] text-[var(--ink-2)] mt-1 max-w-[200px] leading-relaxed">
                    Analyzing floor queues and car state to pick the next dispatch.
                  </p>
                </div>
              )}

              {agenticError ? (
                <div className="flex-1 flex flex-col items-center justify-center p-6 text-center bg-[var(--well)] border border-dashed border-[var(--line)] rounded-lg min-h-[300px]">
                  <AlertCircle className="w-8 h-8 text-[var(--warn-text)] mb-2" />
                  <h4 className="text-sm font-medium text-[var(--ink)]">Agentic run skipped</h4>
                  <p className="text-xs text-[var(--ink-2)] mt-1 max-w-[280px] leading-relaxed">
                    {agenticError.includes('RESOURCE_EXHAUSTED') ?
                      "Gemini rate limits were hit. Pre-recorded presets bypass this, or set your own key in settings." :
                      agenticError}
                  </p>
                  <button
                    onClick={() => setShowSettingsModal(true)}
                    className="mt-3 px-3 py-1.5 bg-transparent border border-[var(--line)] hover:bg-[var(--surface)] rounded-lg text-xs font-medium text-[var(--ink-2)] hover:text-[var(--ink)] transition"
                  >
                    Open settings
                  </button>
                </div>
              ) : (
                <>
                  <ElevatorShaft
                    state={aState}
                    numFloors={floors}
                    numCars={numCars}
                    accent="agent"
                    onFloorClick={isInteractiveMode ? (fIdx) => setActiveSpawnFloor(fIdx) : null}
                  />
                  <ConsoleTerminal logRef={aLogRef} logs={aState.logs} title="Agent event log" />
                </>
              )}
            </div>

          </div>

          {/* Telemetry metrics & Line Chart */}
          <div className="panel p-4 flex flex-col gap-4">
            <div className="flex justify-between items-center border-b border-[var(--line-soft)] pb-2.5">
              <h3 className="text-sm font-medium text-[var(--ink)] m-0 flex items-center gap-1.5">
                <Award className="w-4 h-4 text-[var(--ink-3)]" />
                Performance comparison
              </h3>
              <span className="text-xs text-[var(--ink-3)] font-mono">tick {currentTick}</span>
            </div>

            {/* Delta-first stat strip: hairline dividers via gap-px over the line color */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[var(--line-soft)] border border-[var(--line)] rounded-xl overflow-hidden">
              <MetricComparisonCard
                title="Average wait"
                hVal={heuristicData ? getAverageWaitTimeAtTick(heuristicData.events, currentTick) : 0}
                aVal={agenticData && !agenticError ? getAverageWaitTimeAtTick(agenticData.events, currentTick) : null}
                unit="ticks"
                betterWhen="lower"
                icon={<Clock className="w-3.5 h-3.5" />}
              />
              <MetricComparisonCard
                title="Car moves"
                hVal={hState.rawEvents.filter(e => e.event_type === "CarMoved").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "CarMoved").length : null}
                unit="moves"
                betterWhen="lower"
                icon={<Navigation className="w-3.5 h-3.5" />}
              />
              <MetricComparisonCard
                title="Delivered"
                hVal={hState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length : null}
                unit="pax"
                betterWhen="higher"
                icon={<UserCheck className="w-3.5 h-3.5" />}
              />
              <MetricComparisonCard
                title="Spawned"
                hVal={hState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length}
                aVal={agenticData && !agenticError ? aState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length : null}
                unit="pax"
                betterWhen="neutral"
                icon={<Activity className="w-3.5 h-3.5" />}
              />
              <MetricComparisonCard
                title="Energy"
                hVal={heuristicData ? getEnergyAtTick(heuristicData, currentTick) : 0}
                aVal={agenticData && !agenticError ? getEnergyAtTick(agenticData, currentTick) : null}
                unit="kWh"
                betterWhen="lower"
                icon={<Zap className="w-3.5 h-3.5" />}
              />
            </div>

            {/* Line Chart */}
            <div className="flex flex-col gap-2 mt-1">
              <div className="flex justify-between items-center text-xs">
                <span className="text-[var(--ink-3)]">Average wait over time</span>
                <div className="flex gap-4">
                  <span className="flex items-center gap-1.5 text-[var(--look-text)]">
                    <span className="w-2.5 h-0.5 bg-[var(--look)] inline-block rounded"></span> LOOK
                  </span>
                  <span className="flex items-center gap-1.5 text-[var(--agent-text)]">
                    <span className="w-2.5 h-0.5 border-t border-dashed border-[var(--agent)] inline-block"></span> Gemini
                  </span>
                </div>
              </div>
              <WaitTimeChart
                data={chartData}
                currentTick={currentTick}
                maxWait={maxWaitVal}
                hasAgentic={hasAgenticSeries}
              />
            </div>
          </div>

        </div>

      </div>

      {/* Settings Panel Modal */}
      {showSettingsModal && (
        <SettingsModal
          userApiKey={userApiKey}
          setUserApiKey={setUserApiKey}
          keyChecking={keyChecking}
          keyCheckResult={keyCheckResult}
          handleTestKey={handleTestKey}
          handleSaveSettings={handleSaveSettings}
          llmProvider={llmProvider}
          setLlmProvider={setLlmProvider}
          ollamaHost={ollamaHost}
          setOllamaHost={setOllamaHost}
          ollamaModelId={ollamaModelId}
          setOllamaModelId={setOllamaModelId}
          carSpeeds={carSpeeds}
          setCarSpeeds={setCarSpeeds}
        />
      )}

      {/* Passenger Spawn Destination Selector Modal */}
      {activeSpawnFloor !== null && (
        <PassengerSpawnModal
          activeSpawnFloor={activeSpawnFloor}
          floors={floors}
          spawnPassenger={spawnPassenger}
          onClose={() => setActiveSpawnFloor(null)}
        />
      )}

      {/* Footer */}
      <footer className="mt-12 py-4 border-t border-[var(--line)] text-xs text-[var(--ink-3)] flex justify-between items-center">
        <span>Discrete-event elevator simulator</span>
        <span>Built with Strands, Gemini and Gemma</span>
      </footer>
    </div>
  );
}



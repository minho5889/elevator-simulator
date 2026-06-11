// src/elevatorsim/web/frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import {
  Play, Pause, RotateCcw, ChevronRight, Settings,
  AlertCircle, BookOpen, HelpCircle, Wrench, Languages
} from 'lucide-react';
import { reconstructState, getAverageWaitTimeAtTick, getEnergyAtTick } from './utils/simulationHelper';
import ElevatorShaft from './components/ElevatorShaft';
import ConsoleTerminal from './components/ConsoleTerminal';
import WaitTimeChart from './components/WaitTimeChart';
import SettingsModal from './components/SettingsModal';
import PassengerSpawnModal from './components/PassengerSpawnModal';
import Scoreboard from './components/Scoreboard';
import WinnerBanner from './components/WinnerBanner';
import TourOverlay from './components/TourOverlay';
import HowItWorksModal from './components/HowItWorksModal';
import { useLang } from './i18n.jsx';

const BACKEND_URL = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

const SCENARIOS = [
  { key: 'quiet_day', emoji: '☀️' },
  { key: 'morning_rush', emoji: '🌅' },
  { key: 'evening_rush', emoji: '🌆' },
];

const SPEED_OPTIONS = [
  { ms: 1000, label: '🐢' },
  { ms: 500, label: '🙂' },
  { ms: 250, label: '🐇' },
  { ms: 100, label: '⚡' },
];

export default function App() {
  const { t, lang, setLang } = useLang();

  // App Configurations & Key
  const [userApiKey, setUserApiKey] = useState(() => localStorage.getItem('gemini_api_key') || '');
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [keyChecking, setKeyChecking] = useState(false);
  const [keyCheckResult, setKeyCheckResult] = useState(null);
  const [llmProvider, setLlmProvider] = useState(() => localStorage.getItem('llm_provider') || 'gemini');
  const [ollamaHost, setOllamaHost] = useState(() => localStorage.getItem('ollama_host') || 'http://localhost:11434');
  const [ollamaModelId, setOllamaModelId] = useState(() => localStorage.getItem('ollama_model_id') || 'gemma4:e4b');

  // Friendly-vs-developer surface
  const [advancedMode, setAdvancedMode] = useState(() => localStorage.getItem('advanced_mode') === '1');
  const [showTour, setShowTour] = useState(() => !localStorage.getItem('tour_done'));
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [raceStarted, setRaceStarted] = useState(false);
  const [winnerDismissed, setWinnerDismissed] = useState(false);

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

  useEffect(() => {
    localStorage.setItem('advanced_mode', advancedMode ? '1' : '0');
  }, [advancedMode]);

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
      setSimError(t('error.ws'));
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
    setRaceStarted(false);
    setWinnerDismissed(false);
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
      setKeyCheckResult({ success: false, message: t('settings.keyMissing') });
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
    setRaceStarted(true);
    setWinnerDismissed(false);

    // Instantiate interactive WebSocket session
    initWebSocket();
  };

  const spawnPassenger = (source, target) => {
    if (!isInteractiveMode) return;

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'spawn',
        source: Number(source),
        target: Number(target)
      }));
    } else {
      setSimError(t('error.ws'));
    }
    setActiveSpawnFloor(null);
  };

  const handleRandomSpawn = () => {
    if (!isInteractiveMode) return;

    const source = Math.floor(Math.random() * floors);
    let target = Math.floor(Math.random() * floors);
    while (target === source) {
      target = Math.floor(Math.random() * floors);
    }

    spawnPassenger(source, target);
  };

  const handleRestart = () => {
    setCurrentTick(0);
    setIsPlaying(false);
    setIsAgentThinking(false);
    setWinnerDismissed(false);
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
  };

  const handleStartRace = () => {
    setRaceStarted(true);
    setWinnerDismissed(false);
    if (currentTick >= maxTicks) {
      handleRestart();
      // Restart playback on the next frame so tick resets first
      requestAnimationFrame(() => setIsPlaying(true));
      return;
    }
    setIsPlaying(!isPlaying);
  };

  // Reconstruct States
  const hState = reconstructState(heuristicData?.events, currentTick, numCars);
  const aState = reconstructState(agenticData?.events, currentTick, numCars);

  const hasBrain = !!agenticData && !agenticError;

  // Plain-language scoreboard numbers
  const hWait = heuristicData ? getAverageWaitTimeAtTick(heuristicData.events, currentTick) : 0;
  const aWait = hasBrain ? getAverageWaitTimeAtTick(agenticData.events, currentTick) : null;
  const hDelivered = hState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length;
  const aDelivered = hasBrain ? aState.rawEvents.filter(e => e.event_type === "PassengerDeboarded").length : null;
  const hEnergy = heuristicData ? getEnergyAtTick(heuristicData, currentTick) : 0;
  const aEnergy = hasBrain ? getEnergyAtTick(agenticData, currentTick) : null;

  // Race verdict at the finish line
  const raceOver = raceStarted && maxTicks > 0 && currentTick >= maxTicks;
  let winner = 'tie';
  let winnerPct = 0;
  if (raceOver && hasBrain) {
    const hFinal = getAverageWaitTimeAtTick(heuristicData.events, maxTicks);
    const aFinal = getAverageWaitTimeAtTick(agenticData.events, maxTicks);
    if (aFinal < hFinal) {
      winner = 'brain';
      winnerPct = hFinal > 0 ? Math.round(((hFinal - aFinal) / hFinal) * 100) : 0;
    } else if (hFinal < aFinal) {
      winner = 'robot';
      winnerPct = aFinal > 0 ? Math.round(((aFinal - hFinal) / aFinal) * 100) : 0;
    }
  }
  const showWinner = raceOver && !winnerDismissed && !isInteractiveMode;

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
  const hasAgenticSeries = hasBrain;

  const progressPct = maxTicks > 0 ? Math.min((currentTick / maxTicks) * 100, 100) : 0;

  return (
    // No transform animation on this root: a persistent transform would
    // re-anchor the fixed-position modals/tour to this box, not the viewport
    <div className="container">
      {/* Header */}
      <header className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-6">
        <div>
          <h1 className="display text-3xl sm:text-4xl text-[var(--ink)] m-0 flex items-center gap-2">
            <span className="floaty inline-block select-none" aria-hidden="true">🏢</span>
            {t('app.title')}
          </h1>
          <p className="text-sm font-bold text-[var(--ink-2)] mt-1 mb-0">{t('app.tagline')}</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap" data-tour="header">
          <button
            onClick={() => setShowHowItWorks(true)}
            className="btn-chunky flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold text-[var(--ink-2)]"
          >
            <BookOpen className="w-4 h-4" />
            {t('header.howItWorks')}
          </button>
          <button
            onClick={() => setShowTour(true)}
            className="btn-chunky flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold text-[var(--ink-2)]"
            title={t('header.tour')}
          >
            <HelpCircle className="w-4 h-4" />
            {t('header.tour')}
          </button>
          <button
            onClick={() => setLang(lang === 'en' ? 'ko' : 'en')}
            className="btn-chunky flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold text-[var(--ink-2)]"
            title="Language"
          >
            <Languages className="w-4 h-4" />
            {lang === 'en' ? '한국어' : 'EN'}
          </button>
          <button
            onClick={() => setAdvancedMode(!advancedMode)}
            className="btn-chunky flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold transition-colors text-[var(--ink-2)]"
            // Inline styles: .btn-chunky's background would out-specificity a bg- utility
            style={advancedMode ? { background: 'var(--ink)', color: '#FFF6E5', borderColor: 'var(--ink)' } : undefined}
            aria-pressed={advancedMode}
          >
            <Wrench className="w-4 h-4" />
            {t('header.advanced')}
          </button>
          {advancedMode && (
            <button
              onClick={() => setShowSettingsModal(true)}
              className="btn-chunky flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold text-[var(--ink-2)]"
            >
              <Settings className="w-4 h-4" />
              {t('header.settings')}
            </button>
          )}
        </div>
      </header>

      <main className="flex flex-col gap-6">

        {/* Step 1: pick a day */}
        <section className="panel p-4 sm:p-5" data-tour="scenarios">
          <div className="flex items-baseline gap-3 mb-3 flex-wrap">
            <h2 className="text-lg m-0 text-[var(--ink)]">
              <span className="mr-1.5">📅</span>{t('pickDay.title')}
            </h2>
            <span className="text-xs font-bold text-[var(--ink-3)]">{t('pickDay.hint')}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {SCENARIOS.map(({ key, emoji }) => {
              const active = activePreset === key;
              return (
                <button
                  key={key}
                  onClick={() => handlePresetChange(key)}
                  className={`scenario-card text-left p-4 rounded-2xl border-[2.5px] cursor-pointer ${
                    active
                      ? 'bg-[#FFF3D6] border-[var(--sun-deep)]'
                      : 'bg-[var(--surface)] border-[var(--border-ink)] hover:border-[var(--sun)]'
                  }`}
                  style={{ boxShadow: active ? '0 4px 0 rgba(245,166,35,0.45)' : '0 3px 0 rgba(62,51,88,0.08)' }}
                  aria-pressed={active}
                >
                  <div className="text-3xl mb-1.5 select-none" aria-hidden="true">{emoji}</div>
                  <div className="text-base font-extrabold text-[var(--ink)] [font-family:var(--display)]">
                    {t(`scenario.${key}.name`)}
                  </div>
                  <div className="text-xs font-bold text-[var(--ink-2)] mt-0.5 leading-snug">
                    {t(`scenario.${key}.desc`)}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* Step 2: race controls */}
        <section className="panel p-4 sm:p-5 flex flex-wrap items-center gap-4" data-tour="start">
          <button
            onClick={handleStartRace}
            className="btn-sun flex items-center gap-2 px-7 py-3 text-xl font-extrabold"
          >
            {isPlaying ? (
              <><Pause className="w-6 h-6" /> {t('race.pause')}</>
            ) : (
              <>🏁 {raceStarted && currentTick > 0 && currentTick < maxTicks ? t('race.resume') : t('race.start')}</>
            )}
          </button>

          <button
            onClick={handleRestart}
            className="btn-chunky p-3 text-[var(--ink-2)]"
            title={t('race.restart')}
            aria-label={t('race.restart')}
          >
            <RotateCcw className="w-5 h-5" />
          </button>

          {/* Race progress: a little elevator riding toward the finish flag */}
          <div
            className="flex-1 min-w-[200px] flex items-center gap-2"
            role="progressbar"
            aria-label={t('race.progress')}
            aria-valuenow={currentTick}
            aria-valuemin={0}
            aria-valuemax={maxTicks}
          >
            <div className="flex-1 h-5 rounded-full bg-[var(--well)] border-2 border-[var(--border-ink)] relative overflow-visible">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${progressPct}%`,
                  background: 'linear-gradient(90deg, var(--sun) 0%, var(--sun-deep) 100%)',
                }}
              ></div>
              <span
                className="absolute top-1/2 -translate-y-1/2 text-base select-none transition-all duration-300"
                style={{ left: `calc(${progressPct}% - 10px)` }}
                aria-hidden="true"
              >
                🛗
              </span>
            </div>
            <span className="text-lg select-none" aria-hidden="true">🏁</span>
            {raceOver && (
              <span className="text-xs font-extrabold text-[var(--grass-text)] whitespace-nowrap">
                {t('race.finished')}
              </span>
            )}
          </div>

          {/* Speed: turtle to lightning */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-extrabold text-[var(--ink-3)]">{t('race.speed')}</span>
            <div className="flex gap-1">
              {SPEED_OPTIONS.map(({ ms, label }) => (
                <button
                  key={ms}
                  onClick={() => setPlaybackSpeed(ms)}
                  className={`w-9 h-9 rounded-xl border-2 text-base transition-all cursor-pointer ${
                    playbackSpeed === ms
                      ? 'bg-[var(--sun)] border-[var(--sun-deep)] scale-110'
                      : 'bg-[var(--surface)] border-[var(--border-ink)] hover:border-[var(--sun)]'
                  }`}
                  aria-pressed={playbackSpeed === ms}
                  title={`${(500 / ms).toFixed(1)}x`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Advanced: scrubber + step */}
          {advancedMode && (
            <div className="w-full flex items-center gap-3 pt-3 border-t-2 border-[var(--line-soft)]">
              <span className="text-xs font-bold mono text-[var(--ink)] w-8">{String(currentTick).padStart(3, '0')}</span>
              <input
                type="range" min="0" max={maxTicks} aria-label="Timeline scrubber"
                value={currentTick} onChange={(e) => { setCurrentTick(Number(e.target.value)); setIsPlaying(false); }}
                disabled={isInteractiveMode}
                className="flex-1 accent-[#F5A623] h-1.5 cursor-pointer disabled:opacity-50"
              />
              <span className="text-xs mono text-[var(--ink-3)] w-8">{String(maxTicks).padStart(3, '0')}</span>
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
                className="btn-chunky p-2 text-[var(--ink-2)]"
                title={t('race.step')}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {simError && (
            <p className="w-full text-xs font-bold text-[var(--error-text)] flex items-center gap-1 m-0">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {simError}
            </p>
          )}
        </section>

        {/* Interactive Spawning Helper Banner */}
        {isInteractiveMode && (
          <div className="px-4 py-2.5 flex justify-between items-center bg-[var(--robot-fill)] border-2 border-[var(--robot)] rounded-2xl text-xs slide-up flex-wrap gap-2">
            <span className="flex items-center gap-2 text-[var(--robot-text)] font-extrabold">
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--robot)] pulse-glow"></span>
              {t('live.banner')}
            </span>
            <button
              onClick={handleRandomSpawn}
              className="btn-chunky px-3 py-1.5 text-[11px] font-extrabold text-[var(--robot-text)]"
            >
              🧍 {t('live.spawnRandom')}
            </button>
          </div>
        )}

        {/* The race arena */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative">

          {/* VS badge between the two teams */}
          <div
            className="hidden md:flex absolute left-1/2 top-10 -translate-x-1/2 z-10 w-14 h-14 rounded-full items-center justify-center bg-[var(--sun)] border-[3px] border-[var(--sun-deep)] text-xl font-extrabold text-[#5C3D00] [font-family:var(--display)] wiggle select-none"
            style={{ boxShadow: '0 4px 0 rgba(122,82,0,0.3)' }}
            aria-hidden="true"
          >
            {t('racer.vs')}
          </div>

          {/* Team Rule-Bot */}
          <div className="panel panel-robot p-4 sm:p-5 flex flex-col" data-tour="robot">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-3xl select-none" aria-hidden="true">🤖</span>
              <div>
                <h3 className="text-lg m-0 text-[var(--robot-text)]">{t('racer.robot.name')}</h3>
                <p className="text-xs font-bold text-[var(--ink-2)] m-0">{t('racer.robot.sub')}</p>
              </div>
            </div>

            <ElevatorShaft
              state={hState}
              numFloors={floors}
              numCars={numCars}
              accent="robot"
              onFloorClick={isInteractiveMode ? (fIdx) => setActiveSpawnFloor(fIdx) : null}
            />
            {advancedMode && <ConsoleTerminal logRef={hLogRef} logs={hState.logs} title={t('adv.logs')} />}
          </div>

          {/* Team AI Brain */}
          <div className="panel panel-brain p-4 sm:p-5 flex flex-col relative" data-tour="brain">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-3xl select-none" aria-hidden="true">🧠</span>
              <div>
                <h3 className="text-lg m-0 text-[var(--brain-text)]">{t('racer.brain.name')}</h3>
                <p className="text-xs font-bold text-[var(--ink-2)] m-0">{t('racer.brain.sub')}</p>
              </div>
            </div>

            {isAgentThinking && (
              <div className="absolute inset-0 bg-[rgba(255,246,229,0.9)] rounded-[18px] z-10 flex flex-col items-center justify-center text-center p-6">
                <div className="text-4xl mb-2 floaty select-none" aria-hidden="true">🧠</div>
                <div className="w-8 h-8 rounded-full border-[3px] border-t-[var(--brain)] border-r-transparent border-b-[var(--brain)] border-l-transparent animate-spin mb-3"></div>
                <h4 className="text-base m-0 text-[var(--ink)]">{t('racer.thinking')}</h4>
                <p className="text-xs font-bold text-[var(--ink-2)] mt-1 max-w-[220px] leading-relaxed">
                  {t('racer.thinkingSub')}
                </p>
              </div>
            )}

            {agenticError ? (
              <div className="flex-1 flex flex-col items-center justify-center p-6 text-center bg-[var(--well)] border-2 border-dashed border-[var(--line)] rounded-2xl min-h-[300px]">
                <span className="text-4xl mb-2 select-none" aria-hidden="true">😴</span>
                <h4 className="text-base m-0 text-[var(--ink)]">{t('racer.skipped.title')}</h4>
                <p className="text-xs font-bold text-[var(--ink-2)] mt-1 max-w-[280px] leading-relaxed">
                  {agenticError.includes('RESOURCE_EXHAUSTED') ? t('racer.skipped.rateLimit') : agenticError}
                </p>
                <button
                  onClick={() => setShowSettingsModal(true)}
                  className="btn-chunky mt-3 px-3.5 py-2 text-xs font-extrabold text-[var(--ink-2)]"
                >
                  {t('racer.openSettings')}
                </button>
              </div>
            ) : (
              <>
                <ElevatorShaft
                  state={aState}
                  numFloors={floors}
                  numCars={numCars}
                  accent="brain"
                  onFloorClick={isInteractiveMode ? (fIdx) => setActiveSpawnFloor(fIdx) : null}
                />
                {advancedMode && <ConsoleTerminal logRef={aLogRef} logs={aState.logs} title={t('adv.logs')} />}
              </>
            )}
          </div>

        </div>

        {/* The scoreboard */}
        <Scoreboard
          hWait={hWait} aWait={aWait}
          hDelivered={hDelivered} aDelivered={aDelivered}
          hEnergy={hEnergy} aEnergy={aEnergy}
          hasBrain={hasBrain}
        />

        {/* Gentle pointer to live AI for curious visitors */}
        {!advancedMode && !isInteractiveMode && (
          <p className="text-xs font-bold text-[var(--ink-3)] text-center m-0 px-4">
            💡 {t('live.note')}
          </p>
        )}

        {/* Advanced: build-your-own race + the analytics chart */}
        {advancedMode && (
          <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 slide-up">
            <div className="lg:col-span-4 panel p-4 sm:p-5 flex flex-col gap-4">
              <h2 className="text-lg m-0 text-[var(--ink)]">
                <span className="mr-1.5">🛠️</span>{t('adv.title')}
              </h2>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-extrabold text-[var(--ink-2)]">{t('adv.profile')}</label>
                <select
                  value={profile}
                  onChange={(e) => setProfile(e.target.value)}
                  aria-label={t('adv.profile')}
                  className="w-full bg-[var(--well)] border-2 border-[var(--border-ink)] rounded-xl px-2.5 py-2 text-sm font-semibold outline-none text-[var(--ink)]"
                >
                  <option value="UNIFORM">{t('adv.profile.uniform')}</option>
                  <option value="DOWN_PEAK">{t('adv.profile.down')}</option>
                  <option value="UP_PEAK">{t('adv.profile.up')}</option>
                </select>
              </div>

              {[
                { label: t('adv.arrival'), value: arrivalRate, set: setArrivalRate, min: 0.1, max: 1.0, step: 0.05 },
                { label: t('adv.floors'), value: floors, set: setFloors, min: 5, max: 10, step: 1 },
                { label: t('adv.cars'), value: numCars, set: setNumCars, min: 1, max: 6, step: 1 },
                { label: t('adv.ticks'), value: maxTicks, set: setMaxTicks, min: 30, max: 100, step: 10 },
              ].map(({ label, value, set, min, max, step }) => (
                <div key={label} className="flex flex-col gap-1.5">
                  <label className="text-xs font-extrabold text-[var(--ink-2)] flex justify-between">
                    <span>{label}</span>
                    <span className="mono font-bold text-[var(--ink)]">{value}</span>
                  </label>
                  <input
                    type="range" min={min} max={max} step={step} aria-label={label}
                    value={value} onChange={(e) => set(Number(e.target.value))}
                    className="w-full accent-[#F5A623]"
                  />
                </div>
              ))}

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-extrabold text-[var(--ink-2)]">{t('adv.seed')}</label>
                <input
                  type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} aria-label={t('adv.seed')}
                  className="w-full bg-[var(--well)] border-2 border-[var(--border-ink)] rounded-xl px-2.5 py-2 text-sm outline-none text-[var(--ink)] mono"
                />
              </div>

              <button
                onClick={runCustomSimulation}
                disabled={simulating}
                className="btn-sun w-full mt-1 py-2.5 text-base font-extrabold disabled:opacity-50"
              >
                {simulating ? t('adv.running') : `🔴 ${t('adv.run')}`}
              </button>
              <p className="text-[11px] font-bold text-[var(--ink-3)] m-0 leading-snug">{t('adv.runHint')}</p>
            </div>

            <div className="lg:col-span-8 panel p-4 sm:p-5 flex flex-col gap-3">
              <div className="flex justify-between items-center flex-wrap gap-2">
                <h3 className="text-base m-0 text-[var(--ink)]">
                  <span className="mr-1.5">📈</span>{t('adv.chart')}
                </h3>
                <div className="flex gap-4 text-xs font-extrabold">
                  <span className="flex items-center gap-1.5 text-[var(--robot-text)]">
                    <span className="w-3 h-1 bg-[var(--robot)] inline-block rounded"></span> {t('adv.chartRobot')}
                  </span>
                  <span className="flex items-center gap-1.5 text-[var(--brain-text)]">
                    <span className="w-3 h-1 border-t-2 border-dashed border-[var(--brain)] inline-block"></span> {t('adv.chartBrain')}
                  </span>
                </div>
              </div>
              <WaitTimeChart
                data={chartData}
                currentTick={currentTick}
                maxWait={maxWaitVal}
                hasAgentic={hasAgenticSeries}
              />

              <div className="grid grid-cols-2 gap-3 mt-1">
                <div className="bg-[var(--well)] rounded-xl p-3 text-center">
                  <div className="text-[11px] font-extrabold text-[var(--ink-3)]">🚡 {t('adv.moves')}</div>
                  <div className="text-sm font-extrabold mt-0.5">
                    <span className="text-[var(--robot-text)]">{hState.rawEvents.filter(e => e.event_type === "CarMoved").length}</span>
                    <span className="text-[var(--ink-3)] mx-1.5">·</span>
                    <span className="text-[var(--brain-text)]">{hasBrain ? aState.rawEvents.filter(e => e.event_type === "CarMoved").length : '—'}</span>
                  </div>
                </div>
                <div className="bg-[var(--well)] rounded-xl p-3 text-center">
                  <div className="text-[11px] font-extrabold text-[var(--ink-3)]">🧍 {t('adv.spawned')}</div>
                  <div className="text-sm font-extrabold mt-0.5">
                    <span className="text-[var(--robot-text)]">{hState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length}</span>
                    <span className="text-[var(--ink-3)] mx-1.5">·</span>
                    <span className="text-[var(--brain-text)]">{hasBrain ? aState.rawEvents.filter(e => e.event_type === "PassengerSpawned").length : '—'}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

      </main>

      {/* Winner celebration */}
      {showWinner && (
        <WinnerBanner
          winner={hasBrain ? winner : 'robot'}
          pct={winnerPct}
          onRaceAgain={() => {
            handleRestart();
            setRaceStarted(true);
            requestAnimationFrame(() => setIsPlaying(true));
          }}
          onClose={() => setWinnerDismissed(true)}
        />
      )}

      {/* First-visit guided tour */}
      {showTour && <TourOverlay onFinish={() => setShowTour(false)} />}

      {/* How it works */}
      {showHowItWorks && <HowItWorksModal onClose={() => setShowHowItWorks(false)} />}

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
          onClose={() => setShowSettingsModal(false)}
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
      <footer className="mt-12 py-4 border-t-2 border-[var(--line)] text-xs font-bold text-[var(--ink-3)] flex justify-between items-center flex-wrap gap-2">
        <span>{t('footer.left')}</span>
        <span>{t('footer.right')}</span>
      </footer>
    </div>
  );
}

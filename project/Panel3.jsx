/* global React */
const { useState: uS3, useEffect: uE3, useRef: uR3, useMemo: uM3 } = React;

// Test IDs match the persona_report TestType enum (backend/persona_report/schema.py).
const UNIVERSAL_TESTS = [
  { id: 'accessibility', name: 'Accessibility', desc: 'WCAG 2.2 AA · color contrast, focus order, screen-reader paths.', q: 'Can everyone actually use this product?', cost: 2 },
  { id: 'compliance', name: 'Compliance', desc: 'GDPR, CCPA, SOC-2 touchpoints · consent & data-handling flows.', q: 'Will this get us in legal trouble?', cost: 2 }
];
const PERSONA_TESTS = [
  { id: 'onboarding', name: 'Onboarding', desc: 'First 5 minutes · sign-up, setup, and time-to-value.', q: 'Where do new users drop off before they even start?', cost: 3 },
  { id: 'activation', name: 'Activation', desc: 'Path to the "aha" moment and first meaningful action.', q: 'Do users ever feel the "aha" — and how long does it take?', cost: 3 },
  { id: 'engagement', name: 'Engagement', desc: 'Core-loop friction · do users return to the key surface?', q: 'Is the core loop sticky enough to bring people back?', cost: 4 },
  { id: 'retention', name: 'Retention', desc: 'Day 7 & 30 behavior · churn signals and win-back triggers.', q: 'Why do users stop coming back after week one?', cost: 4 }
];

// Personas / simulation results / report all come from the backend over fetch
// (see project/api.jsx and server/main.py). No mock constants in this file.

function StudioTabs({ step, personaDone, testsPicked, simDone, onStep }) {
  const tabs = [
    { n: 1, label: 'Groups', enabled: true, done: personaDone },
    { n: 2, label: 'Tests', enabled: personaDone, done: testsPicked },
    { n: 3, label: 'Simulation', enabled: testsPicked, done: simDone }
  ];
  return React.createElement('div', { className: 'studio-tabs' },
    tabs.map(t =>
      React.createElement('button', {
        key: t.n,
        className: 'studio-tab' + (step === t.n ? ' active' : '') + (t.done && step !== t.n ? ' done' : '') + (!t.enabled ? ' locked' : ''),
        disabled: !t.enabled,
        onClick: () => t.enabled && onStep(t.n)
      },
        React.createElement('span', { className: 'studio-tab-num' },
          t.done && step !== t.n ? React.createElement(IconCheck) : t.n
        ),
        t.label
      )
    )
  );
}

// Stylized portrait avatars — simple SVG head/shoulders with tunable skin, hair, bg
const Avatar = ({ seed }) => {
  // 3 variants — tuned to match personas below
  const v = [
    { skin: '#e8c39a', hair: '#3d1700', hairPath: 'M28 38 Q28 22 50 22 Q72 22 72 38 L72 46 Q66 30 50 30 Q34 30 28 46 Z', bg: 'var(--terra-tint)', acc: '#c26a43' },
    { skin: '#b98762', hair: '#1a0a00', hairPath: 'M26 42 Q26 18 50 18 Q74 18 74 42 L74 48 Q70 34 60 32 L58 40 L50 34 L42 40 L40 32 Q30 34 26 48 Z', bg: '#e6cfb0', acc: '#3d1700' },
    { skin: '#d9b48f', hair: '#6b3410', hairPath: 'M22 46 Q22 22 50 22 Q78 22 78 44 Q74 38 68 36 Q70 44 68 50 Q60 40 50 40 Q40 40 32 50 Q30 44 32 36 Q26 40 22 46 Z', bg: '#efe3d4', acc: '#c26a43' }
  ][seed % 3];
  return React.createElement('svg', { viewBox: '0 0 100 100', width: 44, height: 44 },
    React.createElement('rect', { width: 100, height: 100, rx: 50, fill: v.bg }),
    // shoulders
    React.createElement('path', { d: 'M10 100 Q10 72 32 68 L68 68 Q90 72 90 100 Z', fill: v.acc, opacity: 0.9 }),
    // neck
    React.createElement('rect', { x: 43, y: 58, width: 14, height: 14, rx: 3, fill: v.skin }),
    // head
    React.createElement('ellipse', { cx: 50, cy: 46, rx: 18, ry: 20, fill: v.skin }),
    // hair
    React.createElement('path', { d: v.hairPath, fill: v.hair }),
    // eyes
    React.createElement('circle', { cx: 43, cy: 48, r: 1.6, fill: '#2a1400' }),
    React.createElement('circle', { cx: 57, cy: 48, r: 1.6, fill: '#2a1400' }),
    // mouth
    React.createElement('path', { d: 'M45 56 Q50 58 55 56', stroke: '#2a1400', strokeWidth: 1.2, fill: 'none', strokeLinecap: 'round' })
  );
};

function DiscoveryGrounding({ methods }) {
  const list = methods || [];
  if (list.length === 0) return null;
  const activeMethods = list.filter(m => m !== 'none');
  const filled = Math.min(activeMethods.length, 5);
  const labels = ['No grounding — simulated only', 'Light grounding', 'Moderate grounding', 'Good grounding', 'Strong grounding', 'Strong grounding'];
  return React.createElement('div', { style: { margin: '12px 0 8px', padding: '10px 12px', background: 'var(--bg-2)', borderRadius: 10, border: '1px solid var(--hair)' } },
    React.createElement('div', { style: { fontSize: 10, color: 'var(--ink-60)', fontFamily: 'Montserrat', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: 6 } }, 'Discovery Grounding'),
    React.createElement('div', { style: { display: 'flex', gap: 4, marginBottom: 6 } },
      Array.from({ length: 5 }, (_, i) =>
        React.createElement('div', {
          key: i,
          style: { flex: 1, height: 7, borderRadius: 999, background: i < filled ? 'var(--terra)' : 'var(--hair-2)', transition: 'background 300ms' }
        })
      )
    ),
    React.createElement('div', { style: { fontSize: 11, color: 'var(--ink-60)' } }, labels[filled])
  );
}

function PersonaSkeletonCard({ i }) {
  return React.createElement('div', { className: 'persona-card', style: { opacity: 1, animation: 'none' } },
    React.createElement('div', { className: 'persona-head' },
      React.createElement('div', { className: 'skel', style: { width: 44, height: 44, borderRadius: '50%' } }),
      React.createElement('div', { style: { flex: 1 } },
        React.createElement('div', { className: 'skel', style: { width: '60%', height: 13, marginBottom: 6 } }),
        React.createElement('div', { className: 'skel', style: { width: '40%', height: 10 } })
      )
    ),
    React.createElement('div', { className: 'persona-attrs' },
      [0, 1, 2, 3].map(k => React.createElement('div', { key: k },
        React.createElement('div', { className: 'skel', style: { width: 40, height: 9, marginBottom: 4 } }),
        React.createElement('div', { className: 'skel', style: { width: '80%', height: 12 } })
      ))
    )
  );
}

function PersonaTab({ synthesis, startError, onStart, onContinue, onReset, intakeContext }) {
  const dots = uM3(() =>
    Array.from({ length: 36 }, () => ({
      sx: (Math.random() - 0.5) * 260 + 'px',
      sy: (Math.random() - 0.5) * 160 + 'px',
      delay: Math.random() * 0.8
    })), []);

  // Derive display phase from the polled run status.
  // synthesis.status: 'idle' | 'running' | 'done' | 'failed'
  let phase;
  if (startError || synthesis.status === 'failed') phase = 'failed';
  else if (synthesis.status === 'running') phase = 'generating';
  else if (synthesis.status === 'done') phase = 'done';
  else phase = 'idle';

  const errorMsg = startError || synthesis.error || 'Synthesis failed.';
  const groups = synthesis.result && synthesis.result.groups ? synthesis.result.groups : [];

  const personas = groups.map((g, i) => ({
    seed: i,
    id: g.id,
    name: g.name,
    role: `${g.demographics.occupation} · ${g.demographics.industry || g.demographics.company_size}`,
    attrs: [
      ['age', g.demographics.age_range],
      ['context', g.demographics.industry || g.demographics.company_size],
      ['goal', (g.narrative.goals && g.narrative.goals[0]) || ''],
      ['blocker', (g.narrative.frustrations && g.narrative.frustrations[0]) || '']
    ]
  }));

  return React.createElement(React.Fragment, null,
    React.createElement('div', { className: 'panel-body' },
    React.createElement('div', { className: 'persona-stage' + (phase === 'generating' ? ' generating' : '') },
      React.createElement('div', { className: 'orbit' },
        dots.map((d, i) =>
          React.createElement('div', {
            key: i,
            className: 'dot' + (i % 4 === 0 ? ' quote' : ''),
            style: {
              '--sx': d.sx, '--sy': d.sy,
              left: '50%', top: '50%',
              animationDelay: `${d.delay}s`
            }
          })
        )
      ),
      React.createElement('div', { className: 'core' }),

      phase === 'idle' && React.createElement('div', {
        style: { position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 20 }
      },
        React.createElement('div', null,
          React.createElement('div', { style: { fontFamily: 'Montserrat', fontSize: 18, fontWeight: 600, marginBottom: 4 } }, 'Ready to synthesize'),
          React.createElement('div', { style: { fontSize: 11.5, color: 'var(--ink-60)' } }, 'Grounded in your files + chat')
        )
      ),
      phase === 'generating' && React.createElement('div', {
        style: { position: 'absolute', bottom: 14, left: 0, right: 0, textAlign: 'center', fontFamily: 'Montserrat', fontSize: 11, color: 'var(--ink-60)' }
      }, 'synthesizing traits · clustering signals · grounding'),
      phase === 'done' && personas.length > 0 && React.createElement('div', { className: 'persona-clusters-beautiful' },
        personas.map((p, i) => {
          const clusterColors = ['#C26A43', '#3d7a8c', '#7a8c3d'];
          const c = clusterColors[i % clusterColors.length];
          const roleLabel = (p.role || '').split('·')[0].trim();
          return React.createElement('div', {
            key: p.id,
            className: 'persona-cluster-card',
            style: { '--cluster-color': c, animationDelay: `${i * 120}ms` }
          },
            React.createElement('div', { className: 'pcc-accent' }),
            React.createElement('div', { className: 'pcc-avatar' }, p.name.charAt(0)),
            React.createElement('div', { className: 'pcc-body' },
              React.createElement('div', { className: 'pcc-name' }, p.name),
              roleLabel && React.createElement('div', { className: 'pcc-role' }, roleLabel)
            ),
            React.createElement('div', { className: 'pcc-badge' })
          );
        })
      ),
      phase === 'done' && React.createElement('div', {
        style: { position: 'absolute', bottom: 10, left: 0, right: 0, textAlign: 'center', fontFamily: 'Montserrat', fontSize: 10.5, color: 'var(--terra)' }
      }, `✓ ${personas.length} persona group${personas.length === 1 ? '' : 's'} synthesized`)
    ),

    phase === 'idle' && React.createElement(DiscoveryGrounding, {
      methods: intakeContext && intakeContext.discoveryMethods
    }),

    phase === 'idle' && React.createElement('button', {
      className: 'btn-primary', style: { width: '100%' }, onClick: onStart
    },
      React.createElement(IconSparkle, { width: 14, height: 14 }),
      'Generate Persona'
    ),

    phase === 'failed' && React.createElement('div', { className: 'error-block' },
      React.createElement('div', { className: 'error-title' }, 'Persona synthesis failed'),
      React.createElement('div', { className: 'error-msg' }, errorMsg),
      React.createElement('button', { className: 'btn-secondary', onClick: onReset }, 'Try again')
    ),

    phase === 'generating' && [1, 2, 3].map(i =>
      React.createElement(PersonaSkeletonCard, { key: `skel-${i}`, i })
    ),

    phase === 'done' && personas.map((p, i) =>
      React.createElement('div', { key: p.name, className: 'persona-card', style: { animationDelay: `${i * 80}ms` } },
        React.createElement('div', { className: 'persona-head' },
          React.createElement(Avatar, { seed: p.seed }),
          React.createElement('div', null,
            React.createElement('div', { className: 'persona-name-row' },
              React.createElement('div', { className: 'persona-name' }, p.name),
              React.createElement('span', { className: 'cluster-badge' }, 'cluster')
            ),
            React.createElement('div', { className: 'persona-role' }, p.role)
          )
        ),
        React.createElement('dl', { className: 'persona-attrs' },
          p.attrs.flatMap(([k, v]) => [
            React.createElement('div', { key: k },
              React.createElement('dt', null, k),
              React.createElement('dd', null, v)
            )
          ])
        )
      )
    )
    ),
    phase === 'done' && React.createElement('div', { className: 'panel-actions' },
      React.createElement('button', {
        className: 'btn-primary',
        onClick: onContinue,
        style: { flex: 'none', padding: '10px 16px' }
      },
        'Continue to tests',
        React.createElement(IconArrow, { width: 14, height: 14 })
      )
    )
  );
}

function getTestConfidence(testId, ctx) {
  if (!ctx) return 'low';
  const productStage = ctx.productStage;
  const discoveryMethods = ctx.discoveryMethods || [];
  const resultsAudience = ctx.resultsAudience || [];
  const hasMethods = discoveryMethods.length > 0 && !discoveryMethods.includes('none');
  // launchFear is now an array of {label, value (0-1), optionValue} from the radar chart
  const fears = Array.isArray(ctx.launchFear) ? ctx.launchFear : [];
  const hasFear = (optVal) => fears.some(f => f.optionValue === optVal && f.value > 0.35);
  if (testId === 'onboarding') return hasFear('signup-dropoff') ? 'high' : productStage ? 'medium' : 'low';
  if (testId === 'activation') return hasMethods && productStage ? 'high' : productStage || hasMethods ? 'medium' : 'low';
  if (testId === 'engagement') return hasMethods ? 'high' : productStage ? 'medium' : 'low';
  if (testId === 'retention') return hasMethods && discoveryMethods.includes('analytics') ? 'high' : hasMethods ? 'medium' : 'low';
  if (testId === 'accessibility') return hasFear('not-accessible') ? 'high' : 'medium';
  if (testId === 'compliance') return (resultsAudience || []).includes('investors') ? 'high' : 'medium';
  return 'medium';
}

function TestsTab({ selected, setSelected, onContinue, intakeContext }) {
  const toggle = (id) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  const total = [...UNIVERSAL_TESTS, ...PERSONA_TESTS].filter(t => selected.includes(t.id)).reduce((a, b) => a + b.cost, 0);

  const renderCard = (t) => {
    const conf = getTestConfidence(t.id, intakeContext);
    const confColor = { high: '#23a66c', medium: '#c98b38', low: '#9b9590' }[conf];
    const confLabel = { high: 'Strong context', medium: 'Directional', low: 'Add more context' }[conf];
    return React.createElement('button', {
      key: t.id,
      className: 'test-card' + (selected.includes(t.id) ? ' selected' : ''),
      onClick: () => toggle(t.id)
    },
      React.createElement('div', { className: 'test-check' }, React.createElement(IconCheck)),
      React.createElement('div', { className: 'test-body' },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 } },
          React.createElement('div', { className: 'test-name' },
            t.name,
            React.createElement('span', {
              title: confLabel,
              style: { width: 7, height: 7, borderRadius: '50%', background: confColor, display: 'inline-block', marginLeft: 6, verticalAlign: 'middle' }
            })
          ),
          React.createElement('span', { className: 'test-cost' }, `${t.cost}k`)
        ),
        React.createElement('div', { className: 'test-desc' }, t.desc),
        React.createElement('div', { className: 'test-q' }, t.q)
      )
    );
  };

  return React.createElement(React.Fragment, null,
    React.createElement('div', { className: 'panel-body' },
      React.createElement('div', { className: 'tests-group' },
        React.createElement('div', { className: 'tests-label' }, 'Universal Tests'),
        UNIVERSAL_TESTS.map(renderCard)
      ),
      React.createElement('div', { className: 'tests-group' },
        React.createElement('div', { className: 'tests-label' }, 'Persona-Specific'),
        PERSONA_TESTS.map(renderCard)
      )
    ),
    React.createElement('div', { className: 'panel-actions' },
      React.createElement('div', { style: { fontSize: 11.5, color: 'var(--ink-60)' } },
        selected.length, ' picked · ',
        React.createElement('strong', { style: { color: 'var(--terra)' } }, total + 'k')
      ),
      React.createElement('button', {
        className: 'btn-primary',
        disabled: selected.length === 0,
        onClick: onContinue,
        style: { flex: 'none', padding: '10px 16px' }
      },
        'Continue',
        React.createElement(IconArrow, { width: 14, height: 14 })
      )
    )
  );
}

const makeSimSteps = (count) => [
  `spinning up ${count} synthetic personas…`,
  'seeding behavioral priors from context…',
  'simulating onboarding paths…',
  'logging friction events & drop-offs…',
  'harvesting verbatim quotes…',
  'scoring & clustering findings…',
  'drafting recommendations…'
];

function SimulationTab({ selected, onDone, simPhase, setSimPhase, tokensUsed,
                         simulation, report, startError, onStart, onReset }) {
  const allTests = [...UNIVERSAL_TESTS, ...PERSONA_TESTS].filter(t => selected.includes(t.id));
  const totalAgents = (simulation.result && simulation.result.report && simulation.result.report.metrics)
    ? simulation.result.report.metrics.total_agents
    : 200;
  const SIM_STEPS = makeSimSteps(totalAgents);
  const [progress, setProgress] = uS3(0);
  const [stepIdx, setStepIdx] = uS3(0);

  // Failure surfaces both at start time and during the run.
  const failed = !!startError || simulation.status === 'failed';
  const errorMsg = startError || simulation.error || 'Simulation failed.';

  // While the run is alive, ramp the existing progress bar to 95% and let the
  // backend completion (App's auto-dispatch on simulation.status==='done')
  // drive the flip to 'done'. No silent fall-through to mock.
  uE3(() => {
    if (simPhase !== 'running') return;
    if (failed) return;
    const start = Date.now();
    const dur = 12000;  // soft estimate; real runs vary widely
    const id = setInterval(() => {
      const p = Math.min(0.95, (Date.now() - start) / dur);
      setProgress(p * 100);
      setStepIdx(Math.min(SIM_STEPS.length - 1, Math.floor(p * SIM_STEPS.length)));
    }, 120);
    return () => clearInterval(id);
  }, [simPhase, failed]);

  uE3(() => {
    if (simulation.status === 'done') {
      setProgress(100);
      setStepIdx(SIM_STEPS.length - 1);
    }
  }, [simulation.status]);

  if (failed && simPhase !== 'confirm') {
    return React.createElement('div', { className: 'panel-body' },
      React.createElement('div', { className: 'error-block' },
        React.createElement('div', { className: 'error-title' }, 'Simulation failed'),
        React.createElement('div', { className: 'error-msg' }, errorMsg),
        React.createElement('button', { className: 'btn-secondary', onClick: () => { onReset(); setSimPhase('confirm'); } }, 'Back to tests')
      )
    );
  }

  if (simPhase === 'confirm') {
    return React.createElement(React.Fragment, null,
      React.createElement('div', { className: 'panel-body' },
        React.createElement('div', { className: 'sim-summary' },
          React.createElement('div', { style: { fontFamily: 'Montserrat', fontWeight: 600, fontSize: 16, marginBottom: 8 } }, 'Confirm simulation'),
          allTests.map(t =>
            React.createElement('div', { key: t.id, className: 'sim-row' },
              React.createElement('span', { className: 'k' }, t.name),
              React.createElement('span', { className: 'v' }, `${t.cost} tk`)
            )
          ),
          React.createElement('div', { className: 'sim-row' },
            React.createElement('span', { className: 'k' }, 'Personas'),
            React.createElement('span', { className: 'v' }, `${totalAgents} synthetic`)
          ),
          React.createElement('div', { className: 'sim-row total' },
            React.createElement('span', { className: 'k' }, 'Total cost'),
            React.createElement('span', { className: 'v' }, `${tokensUsed}k`)
          )
        ),
        React.createElement('div', { style: { fontSize: 12, color: 'var(--ink-60)', lineHeight: 1.55 } },
          'Running this will charge your token balance and spin up the simulation. You\'ll see scored results here when it\'s done (usually < 3 min).'
        )
      ),
      React.createElement('div', { className: 'panel-actions' },
        React.createElement('button', { className: 'btn-secondary', onClick: () => setSimPhase('cancel') }, 'Back'),
        React.createElement('button', {
          className: 'btn-primary',
          onClick: () => { setSimPhase('running'); onStart && onStart(); }
        },
          React.createElement(IconPlay, { width: 12, height: 12 }),
          `Run simulation · ${tokensUsed}k`
        )
      )
    );
  }

  if (simPhase === 'running') {
    return React.createElement('div', { className: 'panel-body' },
      React.createElement('div', { className: 'sim-stage' },
        React.createElement('div', { className: 'sim-globe' },
          React.createElement('svg', { viewBox: '0 0 200 200' },
            [80, 60, 40].map((r, i) =>
              React.createElement('circle', { key: i, cx: 100, cy: 100, r, className: 'sim-ring', style: { opacity: 0.2 + i * 0.15 } })
            ),
            Array.from({ length: 40 }).map((_, i) => {
              const a = (i / 40) * Math.PI * 2 + progress / 30;
              const rr = 30 + ((i * 13) % 55);
              return React.createElement('circle', {
                key: i,
                cx: 100 + Math.cos(a) * rr,
                cy: 100 + Math.sin(a) * rr,
                r: 2 + (i % 3),
                className: 'sim-particle',
                style: { opacity: 0.4 + ((i * 7) % 6) / 10 }
              });
            }),
            React.createElement('circle', { cx: 100, cy: 100, r: 18, fill: 'var(--terra)', style: { opacity: 0.9 } })
          )
        ),
        React.createElement('h3', null, 'Running simulation'),
        React.createElement('p', null, `${totalAgents} personas · `, allTests.length, ' tests'),
        React.createElement('div', { className: 'sim-bar-wrap' },
          React.createElement('div', { className: 'sim-bar', style: { width: `${progress}%` } })
        ),
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', marginTop: 6 } },
          React.createElement('div', { className: 'sim-step' }, SIM_STEPS[stepIdx]),
          React.createElement('div', { className: 'sim-pct' }, `${Math.round(progress)}%`)
        )
      )
    );
  }

  // done — results
  return React.createElement('div', { className: 'panel-body' },
    React.createElement('div', { style: { fontFamily: 'Montserrat', fontWeight: 600, fontSize: 15, marginBottom: 4 } }, 'Results'),
    React.createElement('div', { style: { fontSize: 11.5, color: 'var(--ink-60)', marginBottom: 14 } },
      `${allTests.length} tests · tap any row to open the full report`),
    React.createElement('button', {
      className: 'result-btn',
      style: { background: 'linear-gradient(135deg, var(--ink) 0%, var(--terra) 100%)', marginBottom: 6, border: 'none' },
      onClick: () => window.__openReport('__summary')
    },
      React.createElement('div', {
        className: 'result-score',
        style: { background: 'rgba(255,255,255,0.12)', fontSize: 12, fontWeight: 700, color: 'white' }
      }, '↗'),
      React.createElement('div', { className: 'result-body' },
        React.createElement('div', { className: 'result-name', style: { color: 'white' } }, 'Executive Summary'),
        React.createElement('div', { style: { fontSize: 10, color: 'rgba(255,255,255,0.6)', marginTop: 2 } }, 'Cross-test overview · all clusters')
      ),
      React.createElement('div', { className: 'result-arrow', style: { color: 'rgba(255,255,255,0.5)' } },
        React.createElement(IconArrow, { width: 16, height: 16 })
      )
    ),
    allTests.map((t, i) => {
      const reportReady = report && report.status === 'done' && report.result;
      const tt = reportReady
        ? report.result.test_type_reports.find(r => r.test_type === t.id)
        : null;
      const conf = tt ? tt.data_confidence : (report && report.status === 'failed' ? 'failed' : 'pending');
      const confBg = conf === 'high' ? '#23a66c'
                   : conf === 'medium' ? '#c98b38'
                   : conf === 'low' ? '#b8412b'
                   : conf === 'failed' ? '#b8412b'
                   : '#7a7163';
      return React.createElement('button', {
        key: t.id,
        className: 'result-btn',
        onClick: () => window.__openReport(t.id)
      },
        React.createElement('div', {
          className: 'result-score',
          style: { background: confBg, fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }
        }, conf),
        React.createElement('div', { className: 'result-body' },
          React.createElement('div', { className: 'result-name' }, t.name)
        ),
        React.createElement('div', { className: 'result-arrow' },
          React.createElement(IconArrow, { width: 16, height: 16 })
        )
      );
    })
  );
}

function Studio({ state, dispatch, mockMode, setMockMode,
                  synthesis, simulation, report,
                  onStartSynthesis, onStartSimulation,
                  onResetSynthesis, onResetSimulation,
                  startErrors, intakeContext }) {
  const { step, personaDone, selected, simPhase } = state;
  const tokensUsed = [...UNIVERSAL_TESTS, ...PERSONA_TESTS].filter(t => selected.includes(t.id)).reduce((a, b) => a + b.cost, 0);
  const errs = startErrors || {};

  return React.createElement('section', { className: 'panel enter-3' },
    React.createElement('div', { className: 'panel-head', style: { padding: '14px 20px 10px' } },
      React.createElement('div', { className: 'panel-title' },
        React.createElement(IconTarget, { width: 18, height: 18, style: { color: 'var(--terra)' } }),
        'Studio Space'
      ),
    ),
    React.createElement(StudioTabs, {
      step, personaDone,
      testsPicked: selected.length > 0 && (simPhase === 'done' || step >= 3),
      simDone: simPhase === 'done',
      onStep: (n) => dispatch({ type: 'setStep', step: n })
    }),
    step === 1 && React.createElement(PersonaTab, {
      synthesis,
      startError: errs.synthesis,
      onStart: onStartSynthesis,
      onReset: onResetSynthesis,
      onContinue: () => dispatch({ type: 'setStep', step: 2 }),
      intakeContext
    }),
    step === 2 && React.createElement(TestsTab, {
      selected,
      setSelected: (fn) => dispatch({ type: 'setSelected', selected: typeof fn === 'function' ? fn(selected) : fn }),
      onContinue: () => dispatch({ type: 'goSim' }),
      intakeContext
    }),
    step === 3 && React.createElement(SimulationTab, {
      selected,
      tokensUsed,
      simPhase,
      setSimPhase: (p) => dispatch({ type: 'setSimPhase', simPhase: p }),
      onDone: () => dispatch({ type: 'simDone' }),
      simulation, report,
      startError: errs.simulation,
      onStart: onStartSimulation,
      onReset: onResetSimulation
    }),
    React.createElement('div', { className: 'studio-footer' },
      React.createElement('label', { className: 'mock-toggle' },
        React.createElement('input', {
          type: 'checkbox',
          checked: !!mockMode,
          onChange: (e) => setMockMode && setMockMode(e.target.checked)
        }),
        React.createElement('span', null, 'Mock mode'),
        React.createElement('span', { className: 'mock-hint' },
          mockMode ? 'using bundled fixtures · no Claude calls' : 'live · spends tokens'
        )
      )
    )
  );
}

window.Studio = Studio;
window.UNIVERSAL_TESTS = UNIVERSAL_TESTS;
window.PERSONA_TESTS = PERSONA_TESTS;

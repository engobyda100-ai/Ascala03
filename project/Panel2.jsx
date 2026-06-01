/* global React */
const { useState: useS2, useRef: useR2, useEffect: useE2 } = React;

const COACH_REPLIES = [
  {
    text: "What stage is your product at?",
    interactive: {
      type: 'stage-slider',
      questionId: 'productStage',
      options: [
        { label: 'Idea',               value: 'idea'              },
        { label: 'Problem Validation', value: 'problem-validation' },
        { label: 'Prototype',          value: 'prototype'          },
        { label: 'MVP',                value: 'mvp'                },
        { label: 'Early Traction',     value: 'early-traction'     },
        { label: 'Product-Market Fit', value: 'pmf'                },
        { label: 'Scale',              value: 'scale'              },
      ],
      allowSkip: true, answered: false,
    }
  },
  {
    text: "What are your biggest fears about this launch? Add them to the chart and drag each dot outward to show how worried you are.",
    interactive: {
      type: 'radar',
      questionId: 'launchFear',
      options: [
        { label: "Users won't get it",   value: 'users-wont-get-it'     },
        { label: 'Drop-off at signup',   value: 'signup-dropoff'        },
        { label: 'Not accessible',       value: 'not-accessible'        },
        { label: 'Wrong audience',       value: 'wrong-audience'        },
        { label: 'Poor first impression',value: 'poor-first-impression' },
        { label: 'Pricing resistance',   value: 'pricing-resistance'    },
        { label: 'Complex onboarding',   value: 'complex-onboarding'    },
        { label: 'Low retention',        value: 'low-retention'         },
      ],
      allowSkip: true, answered: false,
    }
  },
  {
    text: "Who's going to read these results?",
    interactive: {
      type: 'multi-chips',
      questionId: 'resultsAudience',
      options: [
        { label: 'Just me (founder)',  value: 'founder'    },
        { label: 'Design team',        value: 'design'     },
        { label: 'Engineering team',   value: 'engineering'},
        { label: 'Investors',          value: 'investors'  },
        { label: 'Whole team',         value: 'whole-team' },
      ],
      allowSkip: true, answered: false,
    }
  },
  {
    text: "Who do you think your target segments are? Drag to rank — most important first.",
    interactive: {
      type: 'drag-rank',
      questionId: 'targetSegments',
      options: [
        { label: 'Startup founders',    value: 'founders'     },
        { label: 'Enterprise PMs',      value: 'enterprise-pms'},
        { label: 'Product designers',   value: 'designers'    },
        { label: 'Software developers', value: 'developers'   },
        { label: 'End consumers',       value: 'consumers'    },
        { label: 'Operations managers', value: 'ops-managers' },
      ],
      allowSkip: true, answered: false,
    }
  },
  {
    text: "Have you done any customer discovery?",
    interactive: {
      type: 'multi-chips',
      questionId: 'discoveryMethods',
      options: [
        { label: 'User interviews', value: 'interviews'     },
        { label: 'Beta testing',    value: 'beta-testing'   },
        { label: 'Surveys',         value: 'surveys'        },
        { label: 'Support tickets', value: 'support-tickets'},
        { label: 'Analytics',       value: 'analytics'      },
        { label: 'None yet',        value: 'none'           },
      ],
      allowSkip: true, answered: false,
    }
  },
  {
    text: "What tests do you care most about right now? Drag to rank — top priority first.",
    interactive: {
      type: 'drag-rank',
      questionId: 'testPriority',
      options: [
        { label: 'Onboarding',   value: 'onboarding'   },
        { label: 'Activation',   value: 'activation'   },
        { label: 'Engagement',   value: 'engagement'   },
        { label: 'Retention',    value: 'retention'    },
        { label: 'Accessibility',value: 'accessibility'},
        { label: 'Compliance',   value: 'compliance'   },
      ],
      allowSkip: true, answered: false,
    }
  },
];

// Question text + option-label maps, keyed by questionId, derived from
// COACH_REPLIES. Published for the centralized intake store (intakeStore.js) so
// it can render readable answer summaries. `problem` is the opening free-text
// question (Chat's first bot message) and has no widget.
const INTAKE_QUESTIONS = COACH_REPLIES.reduce((acc, r) => {
  if (r.interactive) acc[r.interactive.questionId] = r.text;
  return acc;
}, { problem: "What problem does your product solve?" });

const INTAKE_OPTION_LABELS = COACH_REPLIES.reduce((acc, r) => {
  if (r.interactive) {
    acc[r.interactive.questionId] = (r.interactive.options || []).reduce((m, o) => {
      m[o.value] = o.label;
      return m;
    }, {});
  }
  return acc;
}, {});

window.ASCALA_INTAKE_QUESTIONS = INTAKE_QUESTIONS;
window.ASCALA_INTAKE_OPTION_LABELS = INTAKE_OPTION_LABELS;

// Infer likely target segments from the user's free-text problem description.
// Returns up to 6 { label, value } options ranked by relevance signal strength.
function inferTargetSegments(problemText) {
  const t = (problemText || '').toLowerCase();
  const scored = [
    { label: 'Startup founders',     value: 'founders',        score: (t.match(/startup|founder|launch|validate|mvp|idea|early.stage/g) || []).length },
    { label: 'Enterprise teams',     value: 'enterprise-teams',score: (t.match(/enterprise|organization|company|b2b|corporate|scale|large/g) || []).length },
    { label: 'Software developers',  value: 'developers',      score: (t.match(/developer|engineer|code|api|technical|software|engineer/g) || []).length },
    { label: 'Product designers',    value: 'designers',       score: (t.match(/design|ux|ui|visual|prototype|figma|creative|interface/g) || []).length },
    { label: 'Product managers',     value: 'product-pms',     score: (t.match(/product manager|roadmap|feature|prioriti|pm |backlog/g) || []).length },
    { label: 'Marketing teams',      value: 'marketing',       score: (t.match(/marketing|growth|campaign|brand|content|social|audience/g) || []).length },
    { label: 'Sales teams',          value: 'sales',           score: (t.match(/sales|revenue|deal|crm|prospect|customer acquisition/g) || []).length },
    { label: 'Operations managers',  value: 'ops-managers',    score: (t.match(/operation|ops|process|efficiency|automat|workflow|manage/g) || []).length },
    { label: 'End consumers',        value: 'consumers',       score: (t.match(/consumer|personal|individual|people|daily|everyone|anyone|habit/g) || []).length },
    { label: 'Freelancers & agencies', value: 'freelancers',   score: (t.match(/freelancer|agency|consultant|solopreneur|small business/g) || []).length },
  ];
  // Sort by score descending, take top 6; if fewer than 3 scored, add ranked defaults
  const top = scored.filter(s => s.score > 0).sort((a, b) => b.score - a.score).slice(0, 6);
  if (top.length < 3) {
    const defaults = [
      { label: 'Startup founders', value: 'founders' },
      { label: 'Enterprise PMs',   value: 'enterprise-pms' },
      { label: 'Product designers',value: 'designers' },
    ];
    defaults.forEach(d => { if (!top.find(s => s.value === d.value)) top.push({ ...d, score: 0 }); });
  }
  return top.map(({ label, value }) => ({ label, value }));
}

// ─────────────────────────────────────────────────────────────
//  Radar chart
// ─────────────────────────────────────────────────────────────
function RadarQuestion({ q, idx, onSend, onAnswer, onMark }) {
  // viewBox padded so labels always fit
  const VB = 260; const PAD = 44;
  const CX = VB / 2; const CY = VB / 2; const R = 72;

  const svgRef   = useR2(null);
  const confirmed= useR2(false);
  const [fears,       setFears]       = useS2([]);
  const [draggingId,  setDraggingId]  = useS2(null);
  const [customInput, setCustomInput] = useS2('');

  // Reset the double-fire guard whenever the widget is re-opened for editing
  useE2(() => { if (!q.answered) confirmed.current = false; }, [q.answered]);

  const n      = fears.length;
  const angles = Array.from({ length: n }, (_, i) =>
    (i / n) * 2 * Math.PI - Math.PI / 2);

  const addFear = (label, optionValue = null) => {
    const t = label.trim();
    if (!t || fears.find(f => f.label === t)) return;
    setFears(fs => [...fs, { id: Date.now() + Math.random(), label: t, optionValue, severity: 0.5 }]);
  };

  const removeFear = (id) => setFears(fs => fs.filter(f => f.id !== id));

  const getSVGPt = (e) => {
    const svg = svgRef.current; if (!svg) return { x: CX, y: CY };
    const rect = svg.getBoundingClientRect();
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const cy = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: (cx - rect.left) * (VB / rect.width), y: (cy - rect.top) * (VB / rect.height) };
  };

  const onSVGMove = (e) => {
    if (!draggingId) return; e.preventDefault();
    const fi = fears.findIndex(f => f.id === draggingId); if (fi === -1) return;
    const a = angles[fi]; const { x, y } = getSVGPt(e);
    const proj = (x - CX) * Math.cos(a) + (y - CY) * Math.sin(a);
    setFears(fs => fs.map(f => f.id === draggingId
      ? { ...f, severity: Math.max(0.05, Math.min(1, proj / R)) } : f));
  };

  const handleConfirm = () => {
    if (q.answered || confirmed.current) return; confirmed.current = true;
    const result  = fears.map(f => ({ label: f.label, value: f.severity, optionValue: f.optionValue }));
    const summary = fears.length
      ? fears.map(f => `${f.label} (${Math.round(f.severity * 100)}%)`).join(', ')
      : 'No fears specified';
    onSend && onSend(summary);
    onAnswer && onAnswer(q.questionId, result);
    onMark && onMark(idx);
  };

  const filledPts = fears.map((f, i) => {
    const a = angles[i];
    return `${CX + f.severity * R * Math.cos(a)},${CY + f.severity * R * Math.sin(a)}`;
  }).join(' ');

  const RINGS = [0.25, 0.5, 0.75, 1];

  return React.createElement('div', { className: 'interactive-q radar-question' },
    React.createElement('div', { className: 'radar-layout' },

      // ── SVG ───────────────────────────────────────────
      React.createElement('div', { className: 'radar-svg-area' },
        React.createElement('svg', {
          ref: svgRef,
          viewBox: `${-PAD} ${-PAD} ${VB + PAD * 2} ${VB + PAD * 2}`,
          width: '100%',
          style: { display: 'block', userSelect: 'none', overflow: 'visible',
                   cursor: draggingId ? 'grabbing' : 'default' },
          onMouseMove: onSVGMove, onMouseUp: () => setDraggingId(null),
          onMouseLeave: () => setDraggingId(null),
          onTouchMove: onSVGMove, onTouchEnd: () => setDraggingId(null),
        },
          // ── background circles (always visible) ──
          RINGS.map((ratio, ri) =>
            React.createElement('circle', {
              key: 'ring-' + ri, cx: CX, cy: CY, r: ratio * R,
              fill: ri === 3 ? 'var(--bg-2)' : 'none',
              stroke: 'var(--hair)',
              strokeWidth: ri === 3 ? 1.5 : 0.7,
              strokeDasharray: ri < 3 ? '3 3' : undefined,
            })
          ),
          // ring % labels on the vertical axis
          RINGS.slice(0, 3).map((ratio, ri) =>
            React.createElement('text', {
              key: 'rlbl-' + ri,
              x: CX + 3, y: CY - ratio * R + 4,
              fontSize: 7, fill: 'var(--ink-20)',
              fontFamily: 'Dosis, sans-serif',
            }, `${ratio * 100}%`)
          ),
          // ── axis lines ──
          fears.map((f, i) => {
            const a = angles[i];
            return React.createElement('line', {
              key: 'ax-' + f.id,
              x1: CX, y1: CY,
              x2: CX + R * Math.cos(a), y2: CY + R * Math.sin(a),
              stroke: 'var(--hair)', strokeWidth: 1.5,
            });
          }),
          // center dot
          React.createElement('circle', { cx: CX, cy: CY, r: 3, fill: 'var(--ink-40)' }),
          // ── filled polygon ──
          n >= 3 && React.createElement('polygon', {
            points: filledPts,
            fill: 'var(--terra)', fillOpacity: 0.18,
            stroke: 'var(--terra)', strokeWidth: 1.5,
          }),
          n === 2 && React.createElement('line', {
            x1: CX + fears[0].severity * R * Math.cos(angles[0]),
            y1: CY + fears[0].severity * R * Math.sin(angles[0]),
            x2: CX + fears[1].severity * R * Math.cos(angles[1]),
            y2: CY + fears[1].severity * R * Math.sin(angles[1]),
            stroke: 'var(--terra)', strokeWidth: 1.5, strokeOpacity: 0.65,
          }),
          // ── draggable dots ──
          fears.map((f, i) => {
            const a = angles[i];
            return React.createElement('circle', {
              key: 'dot-' + f.id,
              cx: CX + f.severity * R * Math.cos(a),
              cy: CY + f.severity * R * Math.sin(a),
              r: 6, fill: 'var(--terra)', stroke: 'var(--bg)', strokeWidth: 2.5,
              style: { cursor: q.answered ? 'default' : 'grab', filter: draggingId === f.id ? 'drop-shadow(0 0 4px rgba(194,106,67,0.6))' : undefined },
              onMouseDown: q.answered ? undefined : (e) => { e.stopPropagation(); setDraggingId(f.id); },
              onTouchStart: q.answered ? undefined : (e) => { e.preventDefault(); setDraggingId(f.id); },
            });
          }),
          // ── axis labels (Dosis, generous positioning) ──
          fears.map((f, i) => {
            const a = angles[i];
            const dist = R + 18;
            const lx = CX + dist * Math.cos(a);
            const ly = CY + dist * Math.sin(a);
            const anchor = Math.cos(a) > 0.2 ? 'start' : Math.cos(a) < -0.2 ? 'end' : 'middle';
            return React.createElement('text', {
              key: 'lbl-' + f.id, x: lx, y: ly + 4,
              textAnchor: anchor, fontSize: 11,
              fill: 'var(--ink)', fontFamily: 'Dosis, sans-serif',
              fontWeight: 500,
            }, f.label);
          }),
          // empty state
          n === 0 && React.createElement('text', {
            x: CX, y: CY + 24, textAnchor: 'middle', fontSize: 11,
            fill: 'var(--ink-40)', fontFamily: 'Dosis, sans-serif',
          }, 'Add fears →')
        ),

        // ── active fear chips ──
        fears.length > 0 && React.createElement('div', { className: 'radar-active-fears' },
          fears.map(f =>
            React.createElement('span', { key: f.id, className: 'radar-fear-chip' },
              f.label,
              !q.answered && React.createElement('button', {
                className: 'radar-fear-remove',
                onClick: () => removeFear(f.id),
              }, '×')
            )
          )
        ),

        // ── custom input ──
        !q.answered && React.createElement('div', { className: 'radar-add-row' },
          React.createElement('input', {
            type: 'text', placeholder: 'Type a custom fear…',
            className: 'radar-add-input', value: customInput,
            onChange: (e) => setCustomInput(e.target.value),
            onKeyDown: (e) => { if (e.key === 'Enter' && customInput.trim()) { addFear(customInput); setCustomInput(''); } },
          }),
          React.createElement('button', {
            className: 'radar-add-btn', disabled: !customInput.trim(),
            onClick: () => { addFear(customInput); setCustomInput(''); },
          }, '+')
        )
      ),

      // ── suggestions column ──
      !q.answered && React.createElement('div', { className: 'radar-suggestions-panel' },
        React.createElement('div', { className: 'radar-sugg-label' }, 'Suggested'),
        q.options.map((opt, k) => {
          const added = fears.some(f => f.optionValue === opt.value);
          return React.createElement('button', {
            key: k,
            className: 'radar-sugg-chip' + (added ? ' added' : ''),
            disabled: added,
            onClick: () => addFear(opt.label, opt.value),
          }, added ? '✓ ' + opt.label : opt.label);
        })
      )
    ),

    !q.answered && React.createElement('button', {
      className: 'confirm-btn', style: { marginTop: 8 }, onClick: handleConfirm,
    }, 'Confirm →'),
    q.allowSkip && !q.answered && React.createElement('button', {
      className: 'interactive-skip-btn',
      onClick: () => { onSend && onSend('Let Ascala decide'); onAnswer && onAnswer(q.questionId, null); onMark && onMark(idx); },
    }, 'Let Ascala decide →'),
    q.answered && React.createElement('div', { className: 'answered-note' }, 'Answered')
  );
}

// ─────────────────────────────────────────────────────────────
//  Multi-select chips (beautiful toggleable grid + Other input)
// ─────────────────────────────────────────────────────────────
function MultiChipsQuestion({ q, idx, onSend, onAnswer, onMark }) {
  const [selected,     setSelected]     = useS2([]);
  const [customInput,  setCustomInput]  = useS2('');
  const [customOptions,setCustomOptions]= useS2([]);

  const allOptions = [...q.options, ...customOptions];
  const toggle = (v) => setSelected(s => s.includes(v) ? s.filter(x => x !== v) : [...s, v]);

  const addCustom = () => {
    const t = customInput.trim(); if (!t) return;
    const v = 'custom-' + t.toLowerCase().replace(/\s+/g, '-');
    if (allOptions.find(o => o.value === v)) return;
    setCustomOptions(co => [...co, { label: t, value: v }]);
    setSelected(s => [...s, v]);
    setCustomInput('');
  };

  const confirm = () => {
    const picked = allOptions.filter(o => selected.includes(o.value));
    onSend && onSend(picked.length ? picked.map(o => o.label).join(', ') : 'Nothing selected');
    onAnswer && onAnswer(q.questionId, picked.map(o => o.value));
    onMark && onMark(idx);
  };

  return React.createElement('div', { className: 'interactive-q' },
    React.createElement('div', { className: 'multi-chips-grid' },
      allOptions.map((opt, k) => {
        const on = selected.includes(opt.value);
        return React.createElement('button', {
          key: k,
          className: 'multi-chip' + (on ? ' selected' : '') + (q.answered ? ' answered' : ''),
          disabled: q.answered,
          onClick: () => toggle(opt.value),
        },
          React.createElement('span', { className: 'multi-chip-icon' }, on ? '✓' : ''),
          opt.label
        );
      })
    ),
    !q.answered && React.createElement('div', { className: 'multi-chips-other' },
      React.createElement('input', {
        type: 'text', placeholder: 'Other…',
        className: 'multi-chips-input', value: customInput,
        onChange: (e) => setCustomInput(e.target.value),
        onKeyDown: (e) => { if (e.key === 'Enter' && customInput.trim()) addCustom(); },
      }),
      React.createElement('button', {
        className: 'multi-chips-add', disabled: !customInput.trim(), onClick: addCustom,
      }, '+')
    ),
    !q.answered && React.createElement('button', { className: 'confirm-btn', onClick: confirm }, 'Confirm →'),
    q.allowSkip && !q.answered && React.createElement('button', {
      className: 'interactive-skip-btn',
      onClick: () => { onSend && onSend('Let Ascala decide'); onAnswer && onAnswer(q.questionId, null); onMark && onMark(idx); },
    }, 'Let Ascala decide →'),
    q.answered && React.createElement('div', { className: 'answered-note' }, 'Answered')
  );
}

// ─────────────────────────────────────────────────────────────
//  Drag-to-rank (pointer-event drag and drop)
// ─────────────────────────────────────────────────────────────
function DragRankQuestion({ q, idx, onSend, onAnswer, onMark }) {
  const [order,    setOrder]    = useS2(() => (q.options || []).map((_, i) => i));
  const [dragIdx,  setDragIdx]  = useS2(null);
  const listRef    = useR2(null);
  const dragIdxRef = useR2(null);
  const isDragging = dragIdx !== null;

  useE2(() => {
    if (!isDragging) return;

    const onMove = (e) => {
      const list = listRef.current; if (!list || dragIdxRef.current === null) return;
      const clientY = e.clientY ?? (e.touches && e.touches[0].clientY);
      if (clientY == null) return;
      const items = [...list.querySelectorAll('[data-rank-item]')];
      let target = dragIdxRef.current;
      for (let i = 0; i < items.length; i++) {
        const mid = items[i].getBoundingClientRect().top + items[i].offsetHeight / 2;
        if (clientY < mid) { target = i; break; }
        target = i;
      }
      if (target !== dragIdxRef.current) {
        const from = dragIdxRef.current;   // capture before ref is updated
        dragIdxRef.current = target;
        setOrder(o => {
          const next = o.slice();
          const [item] = next.splice(from, 1);
          next.splice(target, 0, item);
          return next;
        });
        setDragIdx(target);
      }
    };

    const onUp = () => { dragIdxRef.current = null; setDragIdx(null); };
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup',   onUp);
    return () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup',   onUp);
    };
  }, [isDragging]);

  const startDrag = (i) => (e) => {
    if (q.answered) return;
    e.preventDefault();
    dragIdxRef.current = i;
    setDragIdx(i);
  };

  const confirm = () => {
    const ordered = order.map(i => q.options[i]);
    onSend && onSend(ordered.map(o => o.label).join(' → '));
    onAnswer && onAnswer(q.questionId, ordered.map(o => o.value));
    onMark && onMark(idx);
  };

  return React.createElement('div', { className: 'interactive-q' },
    React.createElement('div', {
      ref: listRef,
      className: 'rank-list' + (isDragging ? ' rank-dragging' : ''),
    },
      order.map((srcIdx, i) =>
        React.createElement('div', {
          key: q.options[srcIdx].value,
          'data-rank-item': true,
          className: 'rank-item' + (i === dragIdx ? ' rank-item-dragging' : ''),
        },
          React.createElement('div', {
            className: 'drag-handle',
            onPointerDown: startDrag(i),
          },
            React.createElement('span', { className: 'drag-dots' })
          ),
          React.createElement('span', { className: 'rank-num' }, i + 1),
          React.createElement('span', { className: 'rank-label' }, q.options[srcIdx].label)
        )
      )
    ),
    !q.answered && React.createElement('button', { className: 'confirm-btn', onClick: confirm }, 'Confirm order →'),
    q.allowSkip && !q.answered && React.createElement('button', {
      className: 'interactive-skip-btn',
      onClick: () => { onSend && onSend('Let Ascala decide'); onAnswer && onAnswer(q.questionId, null); onMark && onMark(idx); },
    }, 'Let Ascala decide →'),
    q.answered && React.createElement('div', { className: 'answered-note' }, 'Answered')
  );
}

// ─────────────────────────────────────────────────────────────
//  Router — delegates to typed sub-components
// ─────────────────────────────────────────────────────────────
function InteractiveQuestion({ q, idx, onSend, onAnswer, onMark }) {
  const [sliderVal, setSliderVal] = useS2(0);

  if (q.type === 'radar')      return React.createElement(RadarQuestion,     { q, idx, onSend, onAnswer, onMark });
  if (q.type === 'multi-chips')return React.createElement(MultiChipsQuestion, { q, idx, onSend, onAnswer, onMark });
  if (q.type === 'drag-rank')  return React.createElement(DragRankQuestion,   { q, idx, onSend, onAnswer, onMark });

  const skipBtn = q.allowSkip && !q.answered
    ? React.createElement('button', {
        className: 'interactive-skip-btn',
        onClick: () => { onSend && onSend('Let Ascala decide'); onAnswer && onAnswer(q.questionId, null); onMark && onMark(idx); },
      }, 'Let Ascala decide →')
    : null;

  // chips (single-select)
  if (q.type === 'chips') {
    return React.createElement('div', { className: 'interactive-q' },
      React.createElement('div', { className: 'interactive-chips' },
        q.options.map((opt, k) =>
          React.createElement('button', {
            key: k,
            className: 'interactive-chip' + (q.answered ? ' answered' : ''),
            disabled: q.answered,
            onClick: () => { if (!q.answered) { onSend && onSend(opt.label); onAnswer && onAnswer(q.questionId, opt.value); onMark && onMark(idx); } },
          }, opt.label)
        )
      ),
      skipBtn,
      q.answered && React.createElement('div', { className: 'answered-note' }, 'Answered')
    );
  }

  // stage-slider
  if (q.type === 'stage-slider') {
    const max = q.options.length - 1;
    const pct = (sliderVal / max) * 100;
    const nearest = Math.round(sliderVal);
    return React.createElement('div', { className: 'interactive-q' },
      React.createElement('div', { className: 'stage-slider-wrap' },
        React.createElement('div', { className: 'stage-slider-track-wrap' },
          React.createElement('input', {
            type: 'range', min: 0, max, step: 'any',
            value: sliderVal, disabled: q.answered, className: 'stage-slider',
            style: { background: `linear-gradient(to right,var(--terra) 0%,var(--terra) ${pct}%,var(--hair-2) ${pct}%,var(--hair-2) 100%)` },
            onChange: (e) => setSliderVal(Number(e.target.value)),
          }),
          React.createElement('div', { className: 'stage-slider-ticks' },
            q.options.map((_, i) =>
              React.createElement('div', {
                key: i, className: 'stage-tick' + (i === nearest ? ' active' : ''),
                style: { left: `${(i / max) * 100}%` },
              })
            )
          )
        ),
        React.createElement('div', { className: 'stage-slider-labels' },
          q.options.map((opt, i) =>
            React.createElement('span', { key: i, className: 'stage-slider-label' + (i === nearest ? ' active' : '') }, opt.label)
          )
        )
      ),
      !q.answered && React.createElement('button', {
        className: 'confirm-btn',
        onClick: () => { const opt = q.options[nearest]; onSend && onSend(opt.label); onAnswer && onAnswer(q.questionId, opt.value); onMark && onMark(idx); },
      }, 'Confirm →'),
      skipBtn,
      q.answered && React.createElement('div', { className: 'answered-note' }, 'Answered')
    );
  }

  return null;
}

// ─────────────────────────────────────────────────────────────
//  Chat panel
// ─────────────────────────────────────────────────────────────
const TOTAL_INTAKE = COACH_REPLIES.filter(r => r.interactive).length;

function Chat({ onNudgePersona, onMessageSent, onMessagesChange, onIntakeAnswer, onAllAnswered, mockMode }) {
  const [messages, setMessages] = useS2([
    {
      role: 'bot',
      text: "What problem does your product solve?",
      suggestions: ["Saving time on a daily task", "Replacing an expensive tool", "Solving a workflow gap"],
    }
  ]);
  const [draft, setDraft] = useS2('');
  const [recording, setRecording] = useS2(false);
  const [typing, setTyping] = useS2(false);
  const scrollRef      = useR2(null);
  const turnRef        = useR2(0);
  const problemRef     = useR2('');
  const noScrollRef    = useR2(false);
  const closingFiredRef= useR2(false);
  // Flipped to true once every intake widget is answered. Gates the switch from
  // scripted intake into LLM-backed conversation. NOTE: it is intentionally set
  // *after* the final widget's onSend runs, so confirming that widget does not
  // itself fire an LLM turn — only the next typed message does.
  const conversationalRef = useR2(false);
  // Always-current copy of `messages`, so the async LLM call can read the latest
  // conversational history without waiting for a state flush.
  const msgsRef        = useR2(messages);

  useE2(() => {
    if (noScrollRef.current) { noScrollRef.current = false; return; }
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, typing]);

  useE2(() => { msgsRef.current = messages; }, [messages]);
  useE2(() => { if (onMessagesChange) onMessagesChange(messages); }, [messages]);

  const markAnswered = (idx) => setMessages(m => {
    const updated = m.map((msg, i) => i === idx && msg.interactive
      ? { ...msg, interactive: { ...msg.interactive, answered: true } } : msg);
    const done = updated.filter(msg => msg.interactive && msg.interactive.answered).length;
    if (done >= TOTAL_INTAKE && !closingFiredRef.current) {
      closingFiredRef.current = true;
      conversationalRef.current = true;   // every later typed message → LLM
      if (onAllAnswered) onAllAnswered();
      setTimeout(() => setMessages(prev => [...prev, {
        role: 'bot',
        text: "Great — I've got everything I need. What would you like help with?",
        conv: true,
      }]), 700);
    }
    return updated;
  });

  const resetAnswered = (idx) => {
    noScrollRef.current = true;
    setMessages(m =>
      m.map((msg, i) => i === idx && msg.interactive
        ? { ...msg, interactive: { ...msg.interactive, answered: false, reanswer: true } } : msg)
    );
  };

  // Re-answers update intakeContext silently — no message added, no scroll
  const reSendMessage = () => {};

  // Post-intake: send the conversational history + intake summary to the LLM.
  const sendToLLM = (userText) => {
    setTyping(true);
    const prior = (msgsRef.current || []).filter(m => m.conv);
    const apiMessages = [...prior, { role: 'user', text: userText }]
      .map(m => ({ role: m.role === 'bot' ? 'assistant' : 'user', content: m.text }));
    // The Messages API requires the history to begin with a user turn; the
    // closing "What would you like help with?" is an assistant message, so drop
    // any leading assistant turns.
    while (apiMessages.length && apiMessages[0].role !== 'user') apiMessages.shift();
    const system = window.AscalaIntake ? window.AscalaIntake.buildSystemPrompt() : '';
    window.AscalaAPI.chat({ system, messages: apiMessages, mock: mockMode })
      .then(reply => {
        setTyping(false);
        setMessages(m => [...m, { role: 'bot', text: reply || '…', conv: true }]);
      })
      .catch(err => {
        setTyping(false);
        setMessages(m => [...m, {
          role: 'bot', conv: true,
          text: "Sorry — I couldn't reach the model just now. " + (err.message || String(err)),
        }]);
      });
  };

  const sendMessage = (text) => {
    if (!text.trim()) return;
    const clean = text.trim();
    const conversational = conversationalRef.current;
    setMessages(m => [...m, { role: 'user', text: clean, conv: conversational }]);
    setDraft(''); onMessageSent?.();

    // Intake complete → free conversation backed by the LLM.
    if (conversational) { sendToLLM(clean); return; }

    // Otherwise we're still in scripted intake.
    // The opening question ("What problem...") is free text — capture its answer.
    if (turnRef.current === 0) { onIntakeAnswer?.('problem', clean); problemRef.current = clean; }
    if (turnRef.current >= COACH_REPLIES.length) return;
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      const reply = COACH_REPLIES[turnRef.current];
      turnRef.current += 1;
      let interactive = reply.interactive ? { ...reply.interactive } : undefined;
      // Inject inferred segment options when reaching the targetSegments question.
      if (interactive && interactive.questionId === 'targetSegments' && problemRef.current) {
        const inferred = inferTargetSegments(problemRef.current);
        if (inferred.length >= 3) interactive = { ...interactive, options: inferred };
      }
      setMessages(m => [...m, {
        role: 'bot', text: reply.text,
        suggestions: reply.suggestions,
        interactive,
      }]);
      if (turnRef.current >= COACH_REPLIES.length) onNudgePersona?.();
    }, 900 + Math.random() * 500);
  };

  const onKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(draft); } };

  const toggleRecord = () => {
    setRecording(r => !r);
    if (!recording) setTimeout(() => {
      setRecording(false);
      setDraft(d => d + (d ? ' ' : '') + "Our target is early-stage founders validating a B2B tool.");
    }, 1800);
  };

  return React.createElement('section', { className: 'panel enter-2' },
    React.createElement('div', { className: 'chat-head' },
      React.createElement('div', { className: 'chat-head-l' },
        React.createElement('div', { className: 'chat-sigil' },
          React.createElement('img', { src: 'assets/icon.png', alt: 'Ascala', style: { width: '100%', height: '100%', objectFit: 'contain' } })
        ),
        React.createElement('div', null,
          React.createElement('div', { className: 'chat-title' }, 'Ascala Intelligence'),
          React.createElement('div', { className: 'chat-status' }, 'Coaching')
        )
      )
    ),
    React.createElement('div', { className: 'chat-scroll', ref: scrollRef },
      messages.map((m, i) =>
        React.createElement('div', { key: i, className: `msg ${m.role}` },
          React.createElement('div', { className: 'msg-avatar' }, m.role === 'bot' ? 'A' : 'JD'),
          React.createElement('div', { style: { minWidth: 0 } },
            React.createElement('div', { className: 'msg-bubble' },
              m.text.split('\n').map((line, k) => React.createElement('p', { key: k }, line))
            ),
            m.role === 'bot' && m.suggestions && React.createElement('div', { className: 'sugg-row' },
              m.suggestions.map((s, k) =>
                React.createElement('button', { key: k, className: 'sugg-chip', onClick: () => sendMessage(s) }, s)
              )
            ),
            m.role === 'bot' && m.interactive && React.createElement(InteractiveQuestion, {
              q: m.interactive, idx: i,
              onSend: m.interactive.reanswer ? reSendMessage : sendMessage,
              onAnswer: onIntakeAnswer, onMark: markAnswered,
            }),
            m.role === 'user' && messages[i - 1]?.role === 'bot' && messages[i - 1]?.interactive?.answered &&
              React.createElement('div', { style: { display: 'flex', justifyContent: 'flex-end', marginTop: 4 } },
                React.createElement('button', { className: 'reanswer-btn', onClick: () => resetAnswered(i - 1) }, '↩ Change answer')
              )
          )
        )
      ),
      typing && React.createElement('div', { className: 'msg bot' },
        React.createElement('div', { className: 'msg-avatar' }, 'A'),
        React.createElement('div', { className: 'msg-bubble' },
          React.createElement('div', { className: 'typing' },
            React.createElement('span'), React.createElement('span'), React.createElement('span')
          )
        )
      )
    ),
    React.createElement('div', { className: 'chat-input-wrap' },
      React.createElement('div', { className: 'chat-input' },
        React.createElement('textarea', {
          placeholder: 'Message Ascala…', rows: 1, value: draft,
          onChange: (e) => setDraft(e.target.value), onKeyDown: onKey,
        }),
        React.createElement('button', {
          className: 'chat-btn voice' + (recording ? ' recording' : ''),
          onClick: toggleRecord, title: recording ? 'Stop recording' : 'Voice input',
        }, React.createElement(IconMic)),
        React.createElement('button', {
          className: 'chat-btn send', onClick: () => sendMessage(draft), disabled: !draft.trim(),
        }, React.createElement(IconSend))
      ),
      React.createElement('div', { className: 'chat-footnote' }, 'Ascala coaches customer discovery. Responses are suggestions, not gospel.')
    )
  );
}

window.Chat = Chat;

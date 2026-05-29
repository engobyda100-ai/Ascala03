/* global React */
const { useState: uS4, useMemo: uM4, useRef: uR4 } = React;


// ──────────────────── Components ────────────────────

// Map persona_report's TestType to persona_simulation's TestCategory.
// engagement and retention both map to engagement_retention.
const reportToSimCategory = (testType) =>
  (testType === 'engagement' || testType === 'retention') ? 'engagement_retention' : testType;

// Cluster color palette (3 clusters from synthesis)
const CLUSTER_COLORS = { c1: '#c26a43', c2: '#3d7a8c', c3: '#7a8c3d' };
const clusterColor = (cid) => CLUSTER_COLORS[cid] || 'var(--terra)';

function DotDistribution({ distribution, paths }) {
  const { title, description, chart_type, axes, dots, annotations } = distribution;
  const [active, setActive] = uS4(null);
  const [hovered, setHovered] = uS4(null);

  const W = 500, H = 220, PAD_L = 70, PAD_R = 20, PAD_T = 30, PAD_B = 60;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  const xAxis = axes.x;
  const yAxis = axes.y;

  const scaleX = (v) => {
    if (xAxis.categorical) {
      const idx = xAxis.categorical.indexOf(v);
      const denom = Math.max(1, xAxis.categorical.length - 1);
      return PAD_L + (idx / denom) * innerW;
    }
    const min = xAxis.min ?? 0;
    const max = xAxis.max ?? 100;
    return PAD_L + ((Number(v) - min) / (max - min)) * innerW;
  };
  const scaleY = (v) => {
    if (v == null || !yAxis) return PAD_T + innerH / 2;
    if (yAxis.categorical) {
      const idx = yAxis.categorical.indexOf(v);
      const denom = Math.max(1, yAxis.categorical.length - 1);
      return PAD_T + innerH - (idx / denom) * innerH;
    }
    const min = yAxis.min ?? 0;
    const max = yAxis.max ?? 100;
    return PAD_T + innerH - ((Number(v) - min) / (max - min)) * innerH;
  };

  const positions = dots.map(d => ({ ...d, cx: scaleX(d.x), cy: scaleY(d.y) }));

  const activeDot = active != null ? positions[active] : null;
  const activeAgentPath = activeDot ? paths.find(p => p.agent.agent_id === activeDot.agent_id) : null;
  const activeQuote = activeAgentPath ? (
    activeAgentPath.steps.flatMap(s => s.decision.observed_issues).filter(Boolean)[0]
    || activeAgentPath.steps.find(s => s.decision.reasoning)?.decision.reasoning
    || null
  ) : null;
  const activeWho = activeAgentPath ? `Persona · ${activeAgentPath.agent.cluster_name}` : null;

  return React.createElement('div', { className: 'chart-wrap' },
    React.createElement('div', { className: 'chart-title' }, title),
    description && React.createElement('div', { className: 'chart-desc', style: { fontSize: 11, color: 'var(--ink-60)', marginBottom: 6 } }, description),
    React.createElement('svg', { className: 'chart-svg', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' },
      // grid
      [0, 0.25, 0.5, 0.75, 1].map((g, i) => {
        const y = PAD_T + g * innerH;
        return React.createElement('line', {
          key: 'g' + i, x1: PAD_L, x2: W - PAD_R, y1: y, y2: y,
          stroke: 'var(--hair)', strokeWidth: 1, strokeDasharray: i === 4 ? '0' : '2 3'
        });
      }),
      // y-axis labels
      yAxis && [yAxis.min ?? 0, ((yAxis.min ?? 0) + (yAxis.max ?? 100)) / 2, yAxis.max ?? 100].map((val, i) => {
        const y = scaleY(val) + 3;
        return React.createElement('text', {
          key: 'yl' + i, x: PAD_L - 12, y, fontSize: 9, fill: 'var(--ink-40)', fontFamily: 'Montserrat', textAnchor: 'end'
        }, typeof val === 'number' ? Math.round(val) : val);
      }),
      // y-axis title (vertical, parallel to y-axis)
      yAxis && React.createElement('text', {
        key: 'y-title', x: 8, y: PAD_T + innerH / 2,
        fontSize: 10, fill: 'var(--ink-60)', fontFamily: 'Montserrat', fontWeight: 500,
        textAnchor: 'middle', transform: `rotate(-90 8 ${PAD_T + innerH / 2})`
      }, yAxis.label),
      // x-axis labels (at bottom, parallel to x-axis)
      xAxis.categorical && xAxis.categorical.map((cat, i) => {
        const x = scaleX(cat);
        return React.createElement('text', {
          key: 'xl' + i, x, y: PAD_T + innerH + 16,
          fontSize: 9, fill: 'var(--ink-40)', fontFamily: 'Montserrat', textAnchor: 'middle'
        }, cat.length > 12 ? cat.slice(0, 10) + '…' : cat);
      }),
      // x-axis numeric labels (min, mid, max)
      !xAxis.categorical && [xAxis.min ?? 0, ((xAxis.min ?? 0) + (xAxis.max ?? 100)) / 2, xAxis.max ?? 100].map((val, i) => {
        const x = scaleX(val);
        return React.createElement('text', {
          key: 'xl' + i, x, y: PAD_T + innerH + 16,
          fontSize: 9, fill: 'var(--ink-40)', fontFamily: 'Montserrat', textAnchor: 'middle'
        }, typeof val === 'number' ? Math.round(val) : val);
      }),
      // x-axis title
      xAxis && React.createElement('text', {
        key: 'x-title', x: PAD_L + innerW / 2, y: H - 6,
        fontSize: 10, fill: 'var(--ink-60)', fontFamily: 'Montserrat', fontWeight: 500, textAnchor: 'middle'
      }, `${xAxis.label}${xAxis.unit ? ' (' + xAxis.unit + ')' : ''}`),
      // annotations: threshold lines
      annotations.filter(a => a.type === 'threshold').map((a, i) => {
        if (!a.position || a.position.x == null) return null;
        const x = scaleX(a.position.x);
        return React.createElement('line', {
          key: 'th' + i, x1: x, x2: x, y1: PAD_T, y2: PAD_T + innerH,
          stroke: 'var(--ink-40)', strokeWidth: 1, strokeDasharray: '3 3'
        });
      }),
      // hover crosshair lines + axis value labels
      hovered !== null && (() => {
        const hp = positions[hovered];
        const rawX = hp.x;
        const rawY = hp.y;
        const xLabel = typeof rawX === 'number'
          ? `${Math.round(rawX)}${xAxis.unit || ''}`
          : String(rawX ?? '').slice(0, 8);
        const yLabel = rawY != null
          ? `${Math.round(rawY)}${yAxis?.unit || ''}`
          : '';
        const xLabelW = Math.max(28, xLabel.length * 6 + 10);
        const yLabelW = Math.max(24, yLabel.length * 6 + 10);
        return [
          React.createElement('line', {
            key: 'hv', x1: hp.cx, x2: hp.cx, y1: hp.cy, y2: PAD_T + innerH,
            stroke: '#999', strokeWidth: 1, strokeDasharray: '3 3'
          }),
          React.createElement('line', {
            key: 'hh', x1: PAD_L, x2: hp.cx, y1: hp.cy, y2: hp.cy,
            stroke: '#999', strokeWidth: 1, strokeDasharray: '3 3'
          }),
          React.createElement('rect', {
            key: 'xb', x: hp.cx - xLabelW / 2, y: PAD_T + innerH + 26,
            width: xLabelW, height: 13, rx: 3, fill: '#666'
          }),
          React.createElement('text', {
            key: 'xt', x: hp.cx, y: PAD_T + innerH + 35,
            textAnchor: 'middle', fontSize: 8, fill: 'white', fontFamily: 'Montserrat'
          }, xLabel),
          React.createElement('rect', {
            key: 'yb', x: 1, y: hp.cy - 7, width: yLabelW, height: 13, rx: 3, fill: '#666'
          }),
          React.createElement('text', {
            key: 'yt', x: 1 + yLabelW / 2, y: hp.cy + 4,
            textAnchor: 'middle', fontSize: 8, fill: 'white', fontFamily: 'Montserrat'
          }, yLabel)
        ];
      })(),
      // dot labels (abbreviated cluster names)
      positions.map((p, i) =>
        React.createElement('text', {
          key: 'l' + i, x: p.cx, y: p.cy - 9,
          textAnchor: 'middle', fontSize: 8,
          fill: clusterColor(p.cluster_id), fontFamily: 'Montserrat'
        }, p.cluster_name?.split(' ')[0] ?? p.cluster_id)
      ),
      // dots
      positions.map((p, i) =>
        React.createElement('circle', {
          key: 'd' + i, cx: p.cx, cy: p.cy, r: active === i ? 7 : 5,
          className: 'chart-dot',
          fill: clusterColor(p.cluster_id), stroke: 'var(--bg)', strokeWidth: 2,
          onClick: () => setActive(active === i ? null : i),
          onMouseEnter: () => setHovered(i),
          onMouseLeave: () => setHovered(null),
          style: { cursor: 'pointer' }
        })
      )
    ),
    // x-axis labels
    React.createElement('div', { className: 'chart-xlabels' },
      xAxis.categorical
        ? xAxis.categorical.map((l, i) => React.createElement('span', { key: i }, l))
        : [xAxis.min ?? 0, xAxis.max ?? 100].map((v, i) =>
            React.createElement('span', { key: i }, `${v}${xAxis.unit || ''}`))
    ),
    // annotations: text notes
    annotations.filter(a => a.type === 'note' || a.type === 'group_label').length > 0 &&
      React.createElement('div', { style: { fontSize: 11, color: 'var(--ink-60)', marginTop: 6, fontStyle: 'italic' } },
        annotations.filter(a => a.type === 'note' || a.type === 'group_label').map(a => a.text).join(' · ')),
    // quote popup
    activeDot && activeQuote && React.createElement('div', {
      className: 'quote-pop',
      style: {
        left: `${(activeDot.cx / W) * 100}%`,
        top: `${20 + (activeDot.cy / H) * 175}px`
      }
    },
      React.createElement('div', { className: 'who' }, activeWho),
      activeQuote
    )
  );
}

// Trajectory chart: per-cluster frustration arc across screens (1–5).
function TrajectoryChart({ trajectory }) {
  if (!trajectory || !trajectory.cells || trajectory.cells.length === 0) return null;
  const { screens, clusters, cells } = trajectory;
  const W = 500, H = 220, PAD_L = 70, PAD_R = 20, PAD_T = 30, PAD_B = 60;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const xStep = screens.length > 1 ? innerW / (screens.length - 1) : 0;
  const scaleX = (i) => PAD_L + i * xStep;
  const scaleY = (v) => PAD_T + innerH - ((v - 1) / 4) * innerH;

  const byCluster = {};
  for (const cell of cells) {
    if (!byCluster[cell.cluster_id]) byCluster[cell.cluster_id] = [];
    byCluster[cell.cluster_id].push(cell);
  }
  for (const cid in byCluster) byCluster[cid].sort((a, b) => a.screen_index - b.screen_index);

  return React.createElement('div', { className: 'chart-wrap' },
    React.createElement('div', { className: 'chart-title' }, 'Frustration trajectory by cluster'),
    React.createElement('div', { className: 'chart-desc', style: { fontSize: 11, color: 'var(--ink-60)', marginBottom: 6 } },
      'Average frustration (1–5) across the flow per cluster. Crossing 3 (dashed) marks critical friction.'),
    React.createElement('svg', { className: 'chart-svg', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' },
      [1, 2, 3, 4, 5].map((g, i) =>
        React.createElement('line', {
          key: 'g' + i, x1: PAD_L, x2: W - PAD_R, y1: scaleY(g), y2: scaleY(g),
          stroke: 'var(--hair)', strokeWidth: 1, strokeDasharray: g === 3 ? '4 2' : '2 3'
        })
      ),
      [1, 3, 5].map((v, i) =>
        React.createElement('text', { key: 'yl' + i, x: PAD_L - 12, y: scaleY(v) + 3, fontSize: 9, fill: 'var(--ink-40)', fontFamily: 'Montserrat', textAnchor: 'end' }, v)
      ),
      React.createElement('text', {
        key: 'y-title', x: 8, y: PAD_T + innerH / 2,
        fontSize: 10, fill: 'var(--ink-60)', fontFamily: 'Montserrat', fontWeight: 500,
        textAnchor: 'middle', transform: `rotate(-90 8 ${PAD_T + innerH / 2})`
      }, 'Frustration'),
      screens.map((s, i) =>
        React.createElement('text', { key: 'xl' + i, x: scaleX(i), y: H - 12, fontSize: 9, fill: 'var(--ink-40)', textAnchor: 'middle', fontFamily: 'Montserrat' }, s)
      ),
      React.createElement('text', {
        key: 'x-title', x: PAD_L + innerW / 2, y: H - 6,
        fontSize: 10, fill: 'var(--ink-60)', fontFamily: 'Montserrat', fontWeight: 500, textAnchor: 'middle'
      }, 'Screen'),
      clusters.flatMap(cid => {
        const cclls = byCluster[cid] || [];
        if (!cclls.length) return [];
        const points = cclls.map(c => `${scaleX(c.screen_index)},${scaleY(c.emotions.frustration)}`).join(' ');
        const items = [
          React.createElement('polyline', { key: 'ln' + cid, points, fill: 'none', stroke: clusterColor(cid), strokeWidth: 2 })
        ];
        cclls.forEach((c, i) => items.push(React.createElement('circle', {
          key: 'pt' + cid + i,
          cx: scaleX(c.screen_index), cy: scaleY(c.emotions.frustration),
          r: 3, fill: clusterColor(cid), stroke: 'var(--bg)', strokeWidth: 1.5
        })));
        return items;
      })
    ),
    React.createElement('div', { style: { display: 'flex', gap: 10, marginTop: 6, fontSize: 10, color: 'var(--ink-60)' } },
      clusters.map(cid =>
        React.createElement('span', { key: cid, style: { display: 'inline-flex', alignItems: 'center', gap: 4 } },
          React.createElement('span', { style: { width: 10, height: 2, background: clusterColor(cid), display: 'inline-block' } }),
          cid
        )
      )
    )
  );
}

// Compact lift bar shown inside each Fix card.
function LiftBadge({ impact }) {
  if (!impact) return null;
  const conf = impact.confidence || 'low';
  const confBg = conf === 'high' ? '#23a66c' : conf === 'medium' ? '#c98b38' : '#9c9c9c';
  let label;
  if (impact.predicted_lift_pct == null) {
    label = 'Lift: insufficient sibling-path data';
  } else {
    const pct = Math.round(impact.predicted_lift_pct * 100);
    const range = impact.predicted_lift_range;
    const rangeStr = range ? ` (${Math.round(range[0] * 100)}–${Math.round(range[1] * 100)}%)` : '';
    label = `Predicted lift: ${pct >= 0 ? '+' : ''}${pct}%${rangeStr} · n=${impact.sample_size}`;
  }
  return React.createElement('div', {
    style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontSize: 11, color: 'var(--ink-70)' }
  },
    React.createElement('span', {
      style: { background: confBg, color: 'white', padding: '4px 8px', borderRadius: 4, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500 }
    }, conf + ' confid'),
    React.createElement('span', null, label)
  );
}

// Cards for what-if scenarios.
function RetentionSignals({ signals }) {
  if (!signals || signals.length === 0) return null;
  return React.createElement('div', { className: 'rpt-section' },
    React.createElement('h3', null,
      'Signals that would predict better retention',
      React.createElement('span', { className: 'badge' }, '05')
    ),
    React.createElement('ul', { style: { paddingLeft: 18, margin: 0 } },
      signals.map((s, i) =>
        React.createElement('li', { key: i, style: { marginBottom: 6, fontSize: 13 } }, s)
      )
    )
  );
}

function ScenarioCards({ scenarios }) {
  const [selectedScenario, setSelectedScenario] = React.useState(null);

  if (!scenarios || scenarios.length === 0) return null;
  return React.createElement('div', { className: 'rpt-section' },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 } },
      React.createElement('h3', { style: { margin: 0 } }, 'What-if scenarios', React.createElement('span', { className: 'badge' }, '05')),
      React.createElement('div', { style: { display: 'flex', gap: 6, fontSize: 11 } },
        React.createElement('button', {
          onClick: () => setSelectedScenario(null),
          style: {
            padding: '4px 10px',
            borderRadius: 4,
            border: selectedScenario === null ? '1px solid var(--terra)' : '1px solid var(--hair)',
            background: selectedScenario === null ? 'var(--terra-tint)' : 'transparent',
            color: selectedScenario === null ? 'var(--terra)' : 'var(--ink-60)',
            cursor: 'pointer',
            fontWeight: selectedScenario === null ? 500 : 400,
            transition: 'all 160ms ease',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            fontSize: 10
          }
        }, 'All'),
        ...['status_quo', 'quick_win', 'redesign'].map(scenarioType => {
          const label = scenarioType === 'status_quo' ? 'Status quo' : scenarioType === 'quick_win' ? 'Quick win' : 'Redesign';
          return React.createElement('button', {
            key: scenarioType,
            onClick: () => setSelectedScenario(scenarioType),
            style: {
              padding: '4px 10px',
              borderRadius: 4,
              border: selectedScenario === scenarioType ? '1px solid var(--terra)' : '1px solid var(--hair)',
              background: selectedScenario === scenarioType ? 'var(--terra-tint)' : 'transparent',
              color: selectedScenario === scenarioType ? 'var(--terra)' : 'var(--ink-60)',
              cursor: 'pointer',
              fontWeight: selectedScenario === scenarioType ? 500 : 400,
              transition: 'all 160ms ease',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontSize: 10
            }
          }, label);
        })
      )
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 } },
      scenarios
        .filter(s => selectedScenario === null || s.name === selectedScenario)
        .map(s => {
          const hasResidualCounts = s.residual_issue_counts != null;
          const lo = hasResidualCounts ? null : Math.round((s.predicted_completion_rate_low || 0) * 100);
          const hi = hasResidualCounts ? null : Math.round((s.predicted_completion_rate_high || 0) * 100);
          const lift = !hasResidualCounts && (s.predicted_lift_high > 0)
            ? `+${Math.round(s.predicted_lift_low * 100)}–${Math.round(s.predicted_lift_high * 100)}%`
            : '—';
          const issueCountStr = hasResidualCounts
            ? `${s.residual_issue_counts.urgent} critical · ${s.residual_issue_counts.important} important · ${s.residual_issue_counts.medium} medium remaining`
            : null;

          const effortColors = {
            'none': 'var(--ink-40)',
            'small': 'var(--terra)',
            'medium-to-large': '#C26A43'
          };

          return React.createElement('div', {
            key: s.name,
            className: 'scenario-card',
            style: {
              border: '1px solid var(--hair)',
              borderRadius: 8,
              padding: 16,
              background: 'var(--bg)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              transition: 'all 200ms ease',
              boxShadow: 'var(--shadow-panel)',
              cursor: 'pointer',
              position: 'relative',
              overflow: 'hidden'
            },
            onMouseEnter: (e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = 'var(--shadow-pop)';
            },
            onMouseLeave: (e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = 'var(--shadow-panel)';
            }
          },
            // Decorative accent line
            React.createElement('div', {
              style: {
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 3,
                background: s.name === 'status_quo' ? 'var(--ink-40)' : s.name === 'quick_win' ? 'var(--terra)' : '#c98b38',
              }
            }),
            React.createElement('div', { style: { display: 'flex', alignItems: 'baseline', gap: 8, justifyContent: 'space-between' } },
              React.createElement('div', { style: { fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-60)', fontWeight: 500 } }, s.label),
              React.createElement('div', { style: { fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: effortColors[s.effort_estimate] || 'var(--ink-60)', fontWeight: 600 } }, s.effort_estimate.replace('-', '–'))
            ),
            React.createElement('div', { style: { fontSize: hasResidualCounts ? 13 : 28, marginTop: 2, fontFamily: 'Montserrat', lineHeight: hasResidualCounts ? 1.5 : 'inherit', fontWeight: 600, color: 'var(--ink)' } },
              hasResidualCounts ? issueCountStr : (lo === hi ? `${lo}%` : `${lo}–${hi}%`)),
            !hasResidualCounts && React.createElement('div', { style: { fontSize: 10, color: 'var(--ink-60)', marginTop: 2 } }, `Lift ${lift}`),
            React.createElement('div', { style: { fontSize: 12, color: 'var(--ink-70)', lineHeight: 1.4, marginTop: 2 } }, s.description),
            s.fixes_applied && s.fixes_applied.length > 0 && React.createElement('div', { style: { marginTop: 8, paddingTop: 10, borderTop: '1px solid var(--hair)' } },
              React.createElement('div', { style: { fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--ink-40)', marginBottom: 6, fontWeight: 600 } }, 'Changes applied'),
              React.createElement('ul', {
                style: { fontSize: 11, color: 'var(--ink-70)', margin: 0, paddingLeft: 16, lineHeight: 1.5 }
              },
                s.fixes_applied.map((t, i) => React.createElement('li', { key: i }, t))
              )
            )
          );
        })
    )
  );
}

// Outcome context header shown above the per-test "Summary" section.
function OutcomeContextHeader({ ctx }) {
  if (!ctx) return null;
  return React.createElement('div', {
    style: { padding: '10px 12px', background: 'var(--terra-tint)', border: '1px solid var(--hair)', borderRadius: 6, marginBottom: 12 }
  },
    React.createElement('div', { style: { fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-60)' } }, ctx.test_type_metric),
    React.createElement('div', { style: { fontSize: 13, marginTop: 4 } }, ctx.business_implication)
  );
}

// Persona profiles tab — color-coded cards per cluster.
function PersonaProfiles({ paths, clusterFindings }) {
  if (!clusterFindings || clusterFindings.length === 0) return null;

  const clusterStats = {};
  paths.forEach(p => {
    const cid = p.agent.cluster_id;
    if (!clusterStats[cid]) clusterStats[cid] = { ages: [], tech: [], patience: [], devices: [] };
    clusterStats[cid].ages.push(p.agent.age);
    clusterStats[cid].tech.push(p.agent.tech_savviness);
    clusterStats[cid].patience.push(p.agent.patience_threshold);
    clusterStats[cid].devices.push(p.agent.primary_device);
  });

  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 16 } },
    clusterFindings.map(cf => {
      const stats = clusterStats[cf.cluster_id] || { ages: [], tech: [], patience: [], devices: [] };
      const avgAge = stats.ages.length ? Math.round(stats.ages.reduce((a, b) => a + b, 0) / stats.ages.length) : '—';
      const avgTech = stats.tech.length ? (stats.tech.reduce((a, b) => a + b, 0) / stats.tech.length).toFixed(1) : '—';
      const color = clusterColor(cf.cluster_id);
      const rateNum = cf.completion_rate != null ? Math.round(cf.completion_rate * 100) : 0;
      const rateColor = rateNum >= 60 ? '#23a66c' : rateNum >= 40 ? '#c98b38' : '#b8412b';

      return React.createElement('div', {
        key: cf.cluster_id,
        style: {
          borderLeft: `3px solid ${color}`, padding: 16, background: 'var(--bg-alt)',
          borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 12
        }
      },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12 } },
          React.createElement('h4', { style: { margin: 0, color, fontSize: 16 } }, cf.cluster_name),
          React.createElement('div', {
            style: {
              fontSize: 11, fontWeight: 500, color: '#fff', background: rateColor,
              padding: '2px 8px', borderRadius: 3
            }
          }, `${rateNum}% completion`)
        ),
        React.createElement('p', { style: { margin: 0, fontSize: 13, color: 'var(--ink-70)' } }, cf.summary),
        React.createElement('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
          cf.key_friction?.map((friction, i) =>
            React.createElement('span', {
              key: i,
              style: {
                fontSize: 10, padding: '4px 8px', background: 'var(--hair)', borderRadius: 3,
                color: 'var(--ink-60)'
              }
            }, friction)
          )
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, fontSize: 11 } },
          React.createElement('div', null,
            React.createElement('div', { style: { color: 'var(--ink-40)', textTransform: 'uppercase', fontSize: 9 } }, 'Avg age'),
            React.createElement('div', { style: { fontFamily: 'Montserrat', marginTop: 4 } }, avgAge)
          ),
          React.createElement('div', null,
            React.createElement('div', { style: { color: 'var(--ink-40)', textTransform: 'uppercase', fontSize: 9 } }, 'Tech savvy'),
            React.createElement('div', { style: { fontFamily: 'Montserrat', marginTop: 4 } }, avgTech)
          ),
          React.createElement('div', null,
            React.createElement('div', { style: { color: 'var(--ink-40)', textTransform: 'uppercase', fontSize: 9 } }, 'Patience'),
            React.createElement('div', { style: { fontFamily: 'Montserrat', marginTop: 4, fontSize: 10 } },
              stats.patience[0] || '—'
            )
          ),
          React.createElement('div', null,
            React.createElement('div', { style: { color: 'var(--ink-40)', textTransform: 'uppercase', fontSize: 9 } }, 'Device'),
            React.createElement('div', { style: { fontFamily: 'Montserrat', marginTop: 4, fontSize: 10 } },
              stats.devices[0] || '—'
            )
          )
        )
      );
    })
  );
}

// Top-level executive summary banner.
function ExecutiveSummaryBanner({ summary }) {
  if (!summary) return null;
  const overall = Math.round((summary.overall_completion_rate || 0) * 100);
  const worstRate = summary.worst_affected_cluster_rate != null ? Math.round(summary.worst_affected_cluster_rate * 100) : null;
  const bestRate = summary.best_performing_cluster_rate != null ? Math.round(summary.best_performing_cluster_rate * 100) : null;
  const gap = summary.cluster_gap_pct != null ? Math.round(summary.cluster_gap_pct * 100) : null;
  return React.createElement('div', { className: 'rpt-section' },
    React.createElement('h3', null, 'Executive summary', React.createElement('span', { className: 'badge' }, '00')),
    React.createElement('div', { style: { display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' } },
      React.createElement('div', { style: { minWidth: 120 } },
        React.createElement('div', { style: { fontSize: 11, color: 'var(--ink-60)', textTransform: 'uppercase', letterSpacing: '0.08em' } }, 'Overall completion'),
        React.createElement('div', { style: { fontSize: 28, fontFamily: 'Montserrat' } }, `${overall}%`)
      ),
      gap != null && React.createElement('div', { style: { minWidth: 200 } },
        React.createElement('div', { style: { fontSize: 11, color: 'var(--ink-60)', textTransform: 'uppercase', letterSpacing: '0.08em' } }, 'Worst-hit segment'),
        React.createElement('div', { style: { fontSize: 13, marginTop: 4 } },
          `${summary.worst_affected_cluster} (${worstRate}%) trails ${summary.best_performing_cluster} (${bestRate}%) by ${gap} points.`
        )
      ),
      summary.business_summary && React.createElement('div', { style: { flex: 1, minWidth: 240, fontSize: 12, color: 'var(--ink-80)' } },
        summary.business_summary
      )
    ),
    summary.top_blockers_across_tests && summary.top_blockers_across_tests.length > 0 && React.createElement('div', { style: { marginTop: 16 } },
      React.createElement('div', { style: { fontSize: 10, color: 'var(--ink-40)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 10, fontWeight: 600 } }, 'Top blockers across tests'),
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
        summary.top_blockers_across_tests.map((blocker, i) => {
          const rankColors = ['#b8412b', '#c98b38', '#c26a43', '#3d7a8c', '#7a8c3d'];
          const color = rankColors[i] || '#9c9c9c';
          return React.createElement('div', {
            key: i,
            style: {
              display: 'flex', gap: 10, alignItems: 'center',
              padding: '9px 12px',
              background: i === 0 ? 'rgba(184,65,43,0.05)' : 'var(--bg-alt)',
              borderLeft: `3px solid ${color}`,
              borderRadius: '0 6px 6px 0',
              transition: 'background 150ms'
            }
          },
            React.createElement('div', {
              style: {
                minWidth: 20, height: 20, borderRadius: 4, background: color,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, fontWeight: 700, color: 'white',
                fontFamily: 'Montserrat', flexShrink: 0
              }
            }, i + 1),
            React.createElement('div', { style: { fontSize: 12, lineHeight: 1.4, color: 'var(--ink-80)', fontWeight: i === 0 ? 500 : 400 } }, blocker)
          );
        })
      )
    )
  );
}

function SummaryReport({ onClose, simulationResult, report }) {
  const generatedDate = report && report.meta && report.meta.generated_at
    ? new Date(report.meta.generated_at).toLocaleDateString()
    : '—';
  return React.createElement('div', { className: 'report-mask', onClick: onClose },
    React.createElement('div', { className: 'report', onClick: (e) => e.stopPropagation() },
      React.createElement('div', { className: 'report-head' },
        React.createElement('div', {
          className: 'score-big',
          style: { background: 'var(--ink-80)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 8px', textAlign: 'center', lineHeight: 1.2 }
        }, '↗', React.createElement('div', { style: { fontSize: 9, opacity: 0.7, marginTop: 2 } }, 'summary')),
        React.createElement('div', { style: { flex: 1, minWidth: 0 } },
          React.createElement('h2', null, 'Executive summary'),
          React.createElement('div', { className: 'sub' },
            `${simulationResult.report.metrics.total_agents} synthetic personas · ${generatedDate}`)
        ),
        React.createElement('button', { className: 'report-close', onClick: onClose }, React.createElement(IconX))
      ),
      React.createElement('div', { className: 'report-content' },
        React.createElement('div', { className: 'report-main' },
        React.createElement(ExecutiveSummaryBanner, { summary: report.summary }),
        React.createElement('div', { className: 'rpt-section' },
          React.createElement('h3', null, 'Cluster findings'),
          simulationResult.report.cluster_findings.map(cf =>
            React.createElement('div', {
              key: cf.cluster_id,
              style: {
                display: 'flex', gap: 12, padding: 12, marginBottom: 8, background: 'var(--bg-alt)',
                borderLeft: `3px solid ${clusterColor(cf.cluster_id)}`, borderRadius: 4
              }
            },
              React.createElement('div', { style: { flex: 1 } },
                React.createElement('div', { style: { fontSize: 13, fontWeight: 500, color: clusterColor(cf.cluster_id), marginBottom: 4 } }, cf.cluster_name),
                React.createElement('div', { style: { fontSize: 12, color: 'var(--ink-70)' } }, cf.summary)
              ),
              React.createElement('div', { style: { textAlign: 'right', minWidth: 70 } },
                React.createElement('div', { style: { fontSize: 9, color: 'var(--ink-40)', textTransform: 'uppercase' } }, 'Completion'),
                React.createElement('div', {
                  style: {
                    fontSize: 20, fontFamily: 'Montserrat', fontWeight: 500,
                    color: cf.completion_rate >= 0.6 ? '#23a66c' : cf.completion_rate >= 0.4 ? '#c98b38' : '#b8412b'
                  }
                }, `${Math.round(cf.completion_rate * 100)}%`)
              )
            )
          )
        )
        ),
        React.createElement('div', { className: 'persona-card-column', onClick: (e) => e.stopPropagation() },
          React.createElement('div', { className: 'persona-card-header' },
            React.createElement('h3', { style: { margin: 0, fontSize: 16, fontWeight: 600 } }, 'Persona profiles')
          ),
          React.createElement('div', { className: 'persona-card-body' },
            React.createElement(PersonaProfiles, { paths: simulationResult.paths, clusterFindings: simulationResult.report.cluster_findings })
          )
        )
      )
    )
  );
}

function Report({ testId, onClose, simulationResult, report, reportStatus, reportError }) {
  // Hooks must be unconditional — declare before any early return below.
  const [copiedIdx, setCopiedIdx] = uS4(null);

  // No silent fallback to mock data — surface errors and loading explicitly.
  if (reportStatus === 'failed' || reportError) {
    return React.createElement('div', { className: 'report-mask', onClick: onClose },
      React.createElement('div', { className: 'report', onClick: (e) => e.stopPropagation() },
        React.createElement('div', { className: 'report-head' },
          React.createElement('div', { style: { flex: 1 } },
            React.createElement('h2', null, 'Report unavailable')
          ),
          React.createElement('button', { className: 'report-close', onClick: onClose }, React.createElement(IconX))
        ),
        React.createElement('div', { className: 'report-content' },
          React.createElement('div', { className: 'error-block' },
            React.createElement('div', { className: 'error-title' }, 'Report generation failed'),
            React.createElement('div', { className: 'error-msg' }, reportError || 'unknown error')
          )
        )
      )
    );
  }
  if (!report || !simulationResult) {
    return React.createElement('div', { className: 'report-mask', onClick: onClose },
      React.createElement('div', { className: 'report', onClick: (e) => e.stopPropagation() },
        React.createElement('div', { className: 'report-head' },
          React.createElement('div', { style: { flex: 1 } },
            React.createElement('h2', null, 'Generating report…')
          ),
          React.createElement('button', { className: 'report-close', onClick: onClose }, React.createElement(IconX))
        ),
        React.createElement('div', { className: 'report-content' },
          React.createElement('div', { style: { padding: 40, textAlign: 'center', color: 'var(--ink-60)' } },
            'Building your report. This usually takes < 60 seconds in mock mode and several minutes for live runs.'
          )
        )
      )
    );
  }

  if (testId === '__summary') return React.createElement(SummaryReport, { onClose, simulationResult, report });

  const test = [...UNIVERSAL_TESTS, ...PERSONA_TESTS].find(t => t.id === testId);
  const tt = report.test_type_reports.find(r => r.test_type === testId);
  if (!test || !tt) return null;

  const simCategory = reportToSimCategory(tt.test_type);
  const findings = simulationResult.report.categorized_issues.issues
    .filter(issue => issue.category === simCategory)
    .map(issue => ({ t: issue.summary, d: issue.evidence.join(' ') }));

  const generatedDate = report.meta && report.meta.generated_at
    ? new Date(report.meta.generated_at).toLocaleDateString()
    : '—';

  const copy = (i) => {
    const fix = tt.recommended_fixes[i];
    navigator.clipboard?.writeText(fix.fix_prompt);
    setCopiedIdx(i);
    setTimeout(() => setCopiedIdx(null), 1600);
  };

  const confBg = tt.data_confidence === 'high' ? '#23a66c'
               : tt.data_confidence === 'medium' ? '#c98b38'
               : '#b8412b';

  return React.createElement('div', { className: 'report-mask', onClick: onClose },
    React.createElement('div', { className: 'report', onClick: (e) => e.stopPropagation() },
      React.createElement('div', { className: 'report-head' },
        React.createElement('div', {
          className: 'score-big',
          style: { background: confBg, fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 8px', textAlign: 'center', lineHeight: 1.1 }
        }, tt.data_confidence, React.createElement('div', { style: { fontSize: 9, opacity: 0.85, marginTop: 2 } }, 'Conf')),
        React.createElement('div', { style: { flex: 1, minWidth: 0 } },
          React.createElement('h2', null, test.name, ' report'),
          React.createElement('div', { className: 'sub' },
            `${simulationResult.report.metrics.total_agents} synthetic personas · ${generatedDate}`)
        ),
        React.createElement('button', { className: 'report-close', onClick: onClose }, React.createElement(IconX))
      ),
      React.createElement('div', { className: 'report-content' },
        React.createElement('div', { className: 'report-main' },
        React.createElement(OutcomeContextHeader, { ctx: tt.outcome_context }),
        React.createElement('div', { className: 'rpt-section' },
          React.createElement('h3', null, 'Summary', React.createElement('span', { className: 'badge' }, '01')),
          React.createElement('div', { className: 'rpt-summary' },
            React.createElement('p', null, tt.short_summary)
          ),
          React.createElement('div', { className: 'rpt-stats' },
            tt.key_stats.map((s) =>
              React.createElement('div', { key: s.label, className: 'rpt-stat' },
                React.createElement('div', { className: 'k' }, s.label),
                React.createElement('div', { className: 'v' }, s.value)
              )
            )
          )
        ),
        React.createElement('div', { className: 'rpt-section' },
          React.createElement('h3', null, 'Persona distribution',
            React.createElement('span', { className: 'badge' }, '02'),
            React.createElement('span', { className: 'badge', style: { background: 'var(--terra-tint)', color: 'var(--terra)' } }, 'click a dot')
          ),
          tt.persona_distributions.map((pd) =>
            React.createElement(DotDistribution, { key: pd.id, distribution: pd, paths: simulationResult.paths })),
          tt.trajectory && React.createElement(TrajectoryChart, { trajectory: tt.trajectory })
        ),
        React.createElement('div', { className: 'rpt-section' },
          React.createElement('h3', null, 'Key findings', React.createElement('span', { className: 'badge' }, '03')),
          React.createElement('div', { className: 'findings-list' },
            findings.map((f, i) =>
              React.createElement('div', { key: i, className: 'finding' },
                React.createElement('div', { className: 'finding-num' }, i + 1),
                React.createElement('div', { className: 'finding-text' },
                  React.createElement('strong', null, f.t), ' ', f.d
                )
              )
            )
          )
        ),
        React.createElement('div', { className: 'rpt-section' },
          React.createElement('h3', null, 'Recommended fixes', React.createElement('span', { className: 'badge' }, '04')),
          React.createElement('div', { className: 'fixes-list' },
            tt.recommended_fixes.map((f, i) =>
              React.createElement('div', { key: i, className: `fix ${f.severity}` },
                React.createElement('div', { className: 'fix-head' },
                  React.createElement('span', { className: 'fix-prio' }, f.severity),
                  React.createElement('span', { className: 'fix-title' }, f.title)
                ),
                React.createElement('div', { className: 'fix-desc' }, f.summary),
                React.createElement(LiftBadge, { impact: f.counterfactual_impact }),
                React.createElement('div', { className: 'fix-actions' },
                  React.createElement('button', {
                    className: 'fix-btn' + (copiedIdx === i ? ' copied' : ''),
                    onClick: () => copy(i)
                  },
                    React.createElement(copiedIdx === i ? IconCheck : IconCopy),
                    copiedIdx === i ? 'Copied' : 'Copy fix prompt'
                  ),
                  React.createElement('button', { className: 'fix-btn primary' },
                    React.createElement(IconTerminal),
                    'Send to coding agent'
                  )
                )
              )
            )
          )
        ),
        tt.test_type === 'retention'
          ? React.createElement(RetentionSignals, { signals: tt.retention_signals })
          : React.createElement(ScenarioCards, { scenarios: tt.scenarios })
        ),
        React.createElement('div', { className: 'persona-card-column', onClick: (e) => e.stopPropagation() },
          React.createElement('div', { className: 'persona-card-header' },
            React.createElement('h3', { style: { margin: 0, fontSize: 16, fontWeight: 600 } }, 'Persona profiles')
          ),
          React.createElement('div', { className: 'persona-card-body' },
            React.createElement(PersonaProfiles, { paths: simulationResult.paths, clusterFindings: simulationResult.report.cluster_findings })
          )
        )
      )
    )
  );
}

window.Report = Report;

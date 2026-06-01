/* global React */
// Talks to the local FastAPI server defined in /Users/ob/ascala/server/.
// Surface lives at window.AscalaAPI; consumed by Panel3.jsx and Report.jsx.

(function () {
  const cfg = () => window.ASCALA_CONFIG || {};
  const base = () => cfg().API_BASE_URL || 'http://localhost:8000';
  const pollMs = () => cfg().POLL_INTERVAL_MS || 2000;

  async function rawFetch(path, opts) {
    const res = await fetch(base() + path, opts);
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).detail || ''; } catch (_) { detail = await res.text(); }
      throw new Error(`HTTP ${res.status} ${res.statusText}${detail ? ' — ' + JSON.stringify(detail) : ''}`);
    }
    return res.json();
  }

  function startSynthesis({ files, chatTranscript, productUrl, mock }) {
    const fd = new FormData();
    fd.append('chat_transcript', JSON.stringify(chatTranscript || []));
    fd.append('product_url', productUrl || '');
    fd.append('mock', mock ? 'true' : 'false');
    (files || []).forEach((f) => fd.append('files', f, f.name));
    return rawFetch('/api/synthesis/start', { method: 'POST', body: fd })
      .then((r) => r.run_id);
  }

  function startSimulation({ synthesisRunId, screenshots, goal, mock, budgetOverrides }) {
    const fd = new FormData();
    fd.append('synthesis_run_id', synthesisRunId);
    fd.append('goal', goal || '');
    fd.append('mock', mock ? 'true' : 'false');
    if (budgetOverrides) fd.append('budget_overrides', JSON.stringify(budgetOverrides));
    (screenshots || []).forEach((f) => fd.append('screenshots', f, f.name));
    return rawFetch('/api/simulation/start', { method: 'POST', body: fd })
      .then((r) => r.run_id);
  }

  function startReport({ simulationRunId, mock }) {
    return rawFetch('/api/report/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ simulation_run_id: simulationRunId, mock: !!mock }),
    }).then((r) => r.run_id);
  }

  function poll(kind, runId) {
    return rawFetch(`/api/${kind}/${runId}`, { method: 'GET' });
  }

  // Post-intake conversation. `system` carries the intake summary + app
  // instructions; `messages` is the conversational history as
  // [{role:'user'|'assistant', content}]. Resolves to the assistant's reply.
  function chat({ system, messages, mock }) {
    return rawFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system: system || '',
        messages: messages || [],
        mock: !!mock,
      }),
    }).then((r) => r.reply);
  }

  // React hook: poll a run until terminal. runId == null → status: 'idle'.
  function useRun(kind, runId) {
    const [state, setState] = React.useState({ status: runId ? 'running' : 'idle' });
    React.useEffect(() => {
      if (!runId) {
        setState({ status: 'idle' });
        return;
      }
      let alive = true;
      let timeout;
      const tick = async () => {
        try {
          const res = await poll(kind, runId);
          if (!alive) return;
          setState({
            status: res.status,
            result: res.result || null,
            error: res.error || null,
          });
          if (res.status === 'running') {
            timeout = setTimeout(tick, pollMs());
          }
        } catch (e) {
          if (alive) setState({ status: 'failed', error: String(e.message || e) });
        }
      };
      setState({ status: 'running' });
      tick();
      return () => { alive = false; if (timeout) clearTimeout(timeout); };
    }, [kind, runId]);
    return state;
  }

  window.AscalaAPI = { startSynthesis, startSimulation, startReport, poll, useRun, chat };
})();

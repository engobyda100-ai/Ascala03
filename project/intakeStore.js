// Centralized intake store/service.
//
// Holds the single structured intake object for the whole app and lets any
// module read it (or subscribe) without re-querying the chat panel. Loaded as a
// plain <script> before the .jsx bundles, alongside config.js.
//
// Shape:
//   {
//     completed:  boolean,
//     sessionId:  "ses_...",
//     timestamp:  ISO string | null,   // set once, when intake completes
//     questions:  { questionId: "question text", ... },
//     responses:  { questionId: <answer>, ... },
//   }
//
// Writing is one-directional: App (which owns the React source of truth for the
// answers) mirrors its state in here via AscalaIntake.set(). The chat panel and
// any other module read out — buildSystemPrompt()/buildSummary()/get() — so
// there is exactly one writer and no races.

(function () {
  const QUESTIONS = () => window.ASCALA_INTAKE_QUESTIONS || {};
  const OPTION_LABELS = () => window.ASCALA_INTAKE_OPTION_LABELS || {};

  let state = {
    completed: false,
    sessionId: 'ses_' + Math.random().toString(36).slice(2, 14),
    timestamp: null,
    questions: {},
    responses: {},
  };

  const subscribers = new Set();
  const emit = () => subscribers.forEach((fn) => { try { fn(state); } catch (_) {} });

  const get = () => state;
  const set = (patch) => { state = { ...state, ...patch }; emit(); };
  const subscribe = (fn) => { subscribers.add(fn); return () => subscribers.delete(fn); };

  // ── humanize a stored answer using the option labels from the chat config ──
  const labelFor = (qid, value) => {
    const map = OPTION_LABELS()[qid];
    return (map && map[value]) || String(value);
  };

  const summarizeResponse = (qid, value) => {
    if (value == null) return 'Skipped (let Ascala decide)';
    if (Array.isArray(value)) {
      if (value.length === 0) return 'None';
      // radar fears: array of { label, value(severity), optionValue }
      if (typeof value[0] === 'object' && value[0] !== null) {
        return value
          .slice()
          .sort((a, b) => (b.value || 0) - (a.value || 0))
          .map((o) => `${o.label} (${Math.round((o.value || 0) * 100)}%)`)
          .join(', ');
      }
      return value.map((v) => labelFor(qid, v)).join(', ');
    }
    if (typeof value === 'string') {
      // free-text answers (e.g. "problem") pass through; slugs get a label
      return labelFor(qid, value);
    }
    return String(value);
  };

  // A readable bullet list of every answered question, for the system prompt.
  const buildSummary = () => {
    const q = QUESTIONS();
    const lines = [];
    Object.keys(state.responses).forEach((qid) => {
      const v = state.responses[qid];
      if (v == null || (Array.isArray(v) && v.length === 0)) return;
      lines.push(`- ${q[qid] || qid}\n  ${summarizeResponse(qid, v)}`);
    });
    return lines.join('\n');
  };

  // The persistent system prompt: app instructions + intake summary.
  const buildSystemPrompt = (extraInstructions) => {
    const summary = buildSummary();
    return [
      'You are Ascala Intelligence, a product-validation and customer-discovery coach.',
      'You help founders position, price, validate, and launch their product.',
      'Be concise, concrete, and practical.',
      '',
      'System Context — User Intake:',
      summary || '(no intake answers were captured)',
      '',
      'The intake information above is persistent context for every response in this',
      'session. Reference it naturally whenever it is relevant; never ask the intake',
      'questions again.',
      extraInstructions ? '\n' + extraInstructions : '',
    ].join('\n');
  };

  // Optional React hook for components that want to re-render on changes.
  const useIntake = () => {
    const [snap, setSnap] = window.React.useState(state);
    window.React.useEffect(() => subscribe(setSnap), []);
    return snap;
  };

  window.AscalaIntake = {
    get,
    set,
    subscribe,
    buildSummary,
    buildSystemPrompt,
    useIntake,
  };
})();

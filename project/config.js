// Local-dev frontend config. Loaded as a plain <script> before the JSX bundles.
// Override via the in-UI mock-mode toggle, or by editing the values here.
window.ASCALA_CONFIG = {
  API_BASE_URL: 'http://localhost:8000',
  // Default to mock mode so clicking around does not spend Claude credits.
  DEFAULT_MOCK_MODE: true,
  POLL_INTERVAL_MS: 2000,
};

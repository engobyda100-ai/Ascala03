/* global React */
const { useState, useRef, useEffect, useMemo } = React;

function Login({ onEnter }) {
  const [mode, setMode] = useState('login');
  const [leaving, setLeaving] = useState(false);

  const go = () => {
    setLeaving(true);
    setTimeout(onEnter, 520);
  };

  return React.createElement('div', { className: 'login-wrap' + (leaving ? ' leaving' : '') },
    React.createElement('div', { className: 'login-card' },
      React.createElement('img', { src: 'assets/logo.png', alt: 'Ascala', className: 'login-logo' }),
      React.createElement('div', { className: 'login-tag' }, 'Intelligent Validation Studio'),

      React.createElement('div', { className: 'login-tabs' },
        React.createElement('button', { className: 'login-tab' + (mode === 'login' ? ' active' : ''), onClick: () => setMode('login') }, 'Log in'),
        React.createElement('button', { className: 'login-tab' + (mode === 'signup' ? ' active' : ''), onClick: () => setMode('signup') }, 'Sign up')
      ),

      mode === 'signup' && React.createElement('div', { className: 'login-field' },
        React.createElement('label', null, 'Full name'),
        React.createElement('input', { className: 'login-input', placeholder: 'Jane Designer', type: 'text' })
      ),
      React.createElement('div', { className: 'login-field' },
        React.createElement('label', null, 'Email'),
        React.createElement('input', { className: 'login-input', placeholder: 'you@company.com', type: 'email' })
      ),
      React.createElement('div', { className: 'login-field' },
        React.createElement('label', null, 'Password'),
        React.createElement('input', { className: 'login-input', placeholder: '••••••••••', type: 'password' })
      ),

      React.createElement('button', { className: 'login-primary', onClick: go },
        mode === 'login' ? 'Log in' : 'Create account'
      ),

      React.createElement('div', { className: 'login-divider' }, 'or continue with'),

      React.createElement('div', { className: 'oauth-row' },
        React.createElement('button', { className: 'oauth-btn', onClick: go },
          React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24' },
            React.createElement('path', { fill: '#4285F4', d: 'M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z' }),
            React.createElement('path', { fill: '#34A853', d: 'M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A10.98 10.98 0 0 0 12 23z' }),
            React.createElement('path', { fill: '#FBBC05', d: 'M5.84 14.09A6.6 6.6 0 0 1 5.48 12c0-.73.13-1.44.36-2.09V7.07H2.18A10.98 10.98 0 0 0 1 12a10.98 10.98 0 0 0 1.18 4.93l3.66-2.84z' }),
            React.createElement('path', { fill: '#EA4335', d: 'M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z' })
          ),
          'Google'
        ),
        React.createElement('button', { className: 'oauth-btn', onClick: go },
          React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' },
            React.createElement('path', { d: 'M12 .5C5.37.5 0 5.88 0 12.5c0 5.3 3.44 9.8 8.2 11.4.6.1.82-.26.82-.58 0-.28-.01-1.04-.02-2.05-3.34.73-4.04-1.6-4.04-1.6-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.83 1.24 1.83 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.17 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.87.12 3.17.77.84 1.24 1.91 1.24 3.22 0 4.61-2.8 5.62-5.48 5.92.43.37.81 1.1.81 2.22 0 1.61-.01 2.9-.01 3.3 0 .32.22.7.83.58A12 12 0 0 0 24 12.5C24 5.88 18.63.5 12 .5z' })
          ),
          'GitHub'
        )
      ),

      React.createElement('button', { className: 'skip-btn', onClick: go }, 'Skip login for prototype'),
      React.createElement('div', { className: 'login-foot' }, mode === 'login' ? "New here? Switch to sign up above." : 'By signing up, you agree to our Terms.')
    )
  );
}

window.Login = Login;

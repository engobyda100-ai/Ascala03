/* global React */
const { useState: uS1, useRef: uR1 } = React;

const _tb_fmtSize = (bytes) => {
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

function TopBar({ onToggleTheme, dark, tokens,
                  projectName, setProjectName,
                  productUrl, screenshots = [], videos = [], productMode,
                  fileCount = 0, setFiles,
                  onChangePrototype }) {
  const [editingName, setEditingName] = uS1(false);
  const [nameVal, setNameVal] = uS1(projectName || 'Untitled project');
  const addFilesRef = uR1(null);

  const commitName = () => {
    setEditingName(false);
    if (setProjectName) setProjectName(nameVal.trim() || 'Untitled project');
  };

  const handleAddFiles = (e) => {
    if (!setFiles) return;
    const items = Array.from(e.target.files).map(f => ({
      id: Date.now() + Math.random(),
      name: f.name,
      size: _tb_fmtSize(f.size),
      file: f
    }));
    if (items.length) setFiles(fs => [...fs, ...items]);
    e.target.value = '';
  };

  const protoLabel = productUrl
    ? (() => { try { return new URL(productUrl).hostname; } catch (_) { return productUrl.slice(0, 24); } })()
    : screenshots.length > 0 ? `${screenshots.length} screenshot${screenshots.length > 1 ? 's' : ''}`
    : videos.length > 0 ? `${videos.length} video${videos.length > 1 ? 's' : ''}`
    : null;

  const showPills = !!(onChangePrototype || setFiles);

  return React.createElement('header', { className: 'topbar enter' },
    React.createElement('div', { className: 'topbar-left' },
      React.createElement('img', { src: 'assets/logo.png', alt: 'Ascala', className: 'topbar-logo' }),

      editingName && setProjectName
        ? React.createElement('input', {
            className: 'topbar-name-input',
            value: nameVal,
            onChange: (e) => setNameVal(e.target.value),
            onBlur: commitName,
            onKeyDown: (e) => { if (e.key === 'Enter' || e.key === 'Escape') commitName(); },
            autoFocus: true
          })
        : React.createElement('div', {
            className: 'topbar-project',
            onClick: () => { if (setProjectName) { setNameVal(projectName || 'Untitled project'); setEditingName(true); } },
            title: setProjectName ? 'Click to rename' : undefined
          },
            React.createElement('strong', null, projectName || 'Untitled project')
          ),

      showPills && React.createElement('div', { className: 'topbar-pills' },
        React.createElement('button', {
          className: 'topbar-pill',
          onClick: onChangePrototype || undefined,
          style: !onChangePrototype ? { cursor: 'default', pointerEvents: 'none' } : undefined,
          title: onChangePrototype ? 'Change prototype' : undefined,
        },
          React.createElement(IconLink, { width: 11, height: 11 }),
          protoLabel || 'No prototype'
        ),
        React.createElement('button', {
          className: 'topbar-pill',
          onClick: () => addFilesRef.current && addFilesRef.current.click(),
          title: 'Add context files'
        },
          React.createElement(IconFile, { width: 11, height: 11 }),
          fileCount > 0 ? `${fileCount} file${fileCount > 1 ? 's' : ''}` : 'Add context'
        ),
        React.createElement('input', {
          type: 'file', multiple: true,
          accept: '.pdf,.docx,.md,.txt,.csv,.png,.jpg,.jpeg',
          ref: addFilesRef, style: { display: 'none' },
          onChange: handleAddFiles
        })
      )
    ),
    React.createElement('div', { className: 'topbar-right' },
      React.createElement('button', { className: 'tb-btn', onClick: onToggleTheme, title: dark ? 'Light mode' : 'Dark mode' },
        React.createElement(dark ? IconSun : IconMoon, { width: 14, height: 14 })
      ),
      React.createElement('button', { className: 'tb-btn' },
        React.createElement(IconShare, { width: 14, height: 14 }),
        'Share'
      ),
      React.createElement('button', { className: 'tb-btn' },
        React.createElement(IconSettings, { width: 14, height: 14 }),
        'Settings'
      ),
      React.createElement('button', { className: 'tb-btn tokens' },
        React.createElement(IconCoin, { width: 14, height: 14 }),
        'Tokens ', tokens
      ),
      React.createElement('button', { className: 'tb-btn', style: { paddingLeft: 4, paddingRight: 4 } },
        React.createElement('div', { className: 'tb-avatar' }, 'JD')
      )
    )
  );
}

window.TopBar = TopBar;

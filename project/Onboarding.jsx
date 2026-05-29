/* global React */
const { useState, useRef } = React;

const _fmtSize = (bytes) => {
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

function Onboarding({ files, setFiles, productMode, setProductMode, productUrl, setProductUrl, screenshots, setScreenshots, videos, setVideos, dark, onToggleTheme, tokens, onContinue, projectName, setProjectName }) {
  const [urlDraft, setUrlDraft] = useState(productUrl || '');
  const shotInputRef = useRef(null);
  const videoInputRef = useRef(null);
  const contextInputRef = useRef(null);

  const handleShotFiles = (e) => {
    const items = Array.from(e.target.files).map(f => ({
      id: Date.now() + Math.random(),
      name: f.name,
      url: URL.createObjectURL(f),
      size: _fmtSize(f.size),
      file: f
    }));
    setScreenshots(s => [...s, ...items]);
    e.target.value = '';
  };

  const handleVideoFiles = (e) => {
    const items = Array.from(e.target.files).map(f => ({
      id: Date.now() + Math.random(),
      name: f.name,
      size: _fmtSize(f.size),
      file: f
    }));
    setVideos(v => [...v, ...items]);
    e.target.value = '';
  };

  const handleContextFiles = (e) => {
    const items = Array.from(e.target.files).map(f => ({
      id: Date.now() + Math.random(),
      name: f.name,
      size: _fmtSize(f.size),
      file: f
    }));
    setFiles(f => [...f, ...items]);
    e.target.value = '';
  };

  const canContinue = Boolean(productUrl || screenshots.length > 0 || videos.length > 0);

  return React.createElement('div', { className: 'onboarding-stage' },
    React.createElement(window.TopBar, { dark, onToggleTheme, tokens, projectName, setProjectName }),
    React.createElement('div', { className: 'onboarding-body' },
      React.createElement('div', { className: 'onboarding-card' },

        // Header
        React.createElement('div', { className: 'onboarding-header' },
          React.createElement('h1', { className: 'onboarding-title' }, 'What are you validating?'),
          React.createElement('p', { className: 'onboarding-subtitle' },
            'Add your prototype — Ascala will synthesize personas and run behavioral simulations against it.'
          )
        ),

        // Prototype section
        React.createElement('div', { className: 'onboarding-section' },
          React.createElement('div', { className: 'onboarding-section-label' }, 'Prototype'),
          React.createElement('div', { className: 'toggle-row' },
            React.createElement('button', { className: 'toggle-btn' + (productMode === 'url' ? ' active' : ''), onClick: () => setProductMode('url') },
              React.createElement(IconLink, null), 'Link'
            ),
            React.createElement('button', { className: 'toggle-btn' + (productMode === 'images' ? ' active' : ''), onClick: () => setProductMode('images') },
              React.createElement(IconImage, null), 'Screenshots'
            ),
            React.createElement('button', { className: 'toggle-btn' + (productMode === 'video' ? ' active' : ''), onClick: () => setProductMode('video') },
              React.createElement(IconVideo, null), 'Video'
            )
          ),

          // URL tab
          productMode === 'url' && React.createElement('div', null,
            React.createElement('div', { className: 'url-input-row' },
              React.createElement('input', {
                className: 'url-input',
                placeholder: 'https://your-prototype.com',
                value: urlDraft,
                onChange: (e) => setUrlDraft(e.target.value),
                onKeyDown: (e) => { if (e.key === 'Enter') setProductUrl(urlDraft); }
              }),
              React.createElement('button', { className: 'url-submit', onClick: () => setProductUrl(urlDraft) }, 'Add')
            ),
            productUrl && React.createElement('div', { className: 'file-chip' },
              React.createElement(IconLink, null),
              React.createElement('span', { className: 'fname' }, productUrl),
              React.createElement('span', { className: 'fsize' }, 'linked'),
              React.createElement('button', { className: 'chip-del', onClick: () => { setProductUrl(''); setUrlDraft(''); } },
                React.createElement(IconX, { width: 9, height: 9 })
              )
            )
          ),

          // Screenshots tab
          productMode === 'images' && React.createElement('div', null,
            React.createElement('input', {
              type: 'file', accept: 'image/*', multiple: true,
              ref: shotInputRef, style: { display: 'none' },
              onChange: handleShotFiles
            }),
            screenshots.length === 0
              ? React.createElement('div', { className: 'dropzone', onClick: () => shotInputRef.current.click() },
                  React.createElement(IconImage, null),
                  React.createElement('strong', null, 'Drop screenshots or click'),
                  React.createElement('span', null, 'PNG, JPG · up to 20 files')
                )
              : React.createElement('div', { className: 'shot-strip' },
                  screenshots.map(s =>
                    React.createElement('div', { key: s.id, className: 'shot-thumb' },
                      React.createElement('img', { src: s.url, alt: s.name, draggable: false }),
                      React.createElement('button', { className: 'shot-del', onClick: () => setScreenshots(ss => ss.filter(x => x.id !== s.id)) },
                        React.createElement(IconX, { width: 8, height: 8 })
                      )
                    )
                  ),
                  React.createElement('button', { className: 'shot-add', onClick: () => shotInputRef.current.click() },
                    React.createElement(IconImage, { width: 16, height: 16 }),
                    'Add more'
                  )
                )
          ),

          // Video tab
          productMode === 'video' && React.createElement('div', null,
            React.createElement('input', {
              type: 'file', accept: 'video/*',
              ref: videoInputRef, style: { display: 'none' },
              onChange: handleVideoFiles
            }),
            React.createElement('div', { className: 'dropzone', onClick: () => videoInputRef.current.click() },
              React.createElement(IconVideo, null),
              React.createElement('strong', null, 'Drop a walkthrough video'),
              React.createElement('span', null, 'MP4, MOV · up to 200 MB')
            ),
            videos.map(v =>
              React.createElement('div', { key: v.id, className: 'file-chip' },
                React.createElement(IconVideo, null),
                React.createElement('span', { className: 'fname' }, v.name),
                React.createElement('span', { className: 'fsize' }, v.size),
                React.createElement('button', { className: 'chip-del', onClick: () => setVideos(vs => vs.filter(x => x.id !== v.id)) },
                  React.createElement(IconX, { width: 9, height: 9 })
                )
              )
            )
          )
        ),

        // Context Files section
        React.createElement('div', { className: 'onboarding-section' },
          React.createElement('div', { className: 'onboarding-section-label' },
            'Context Files',
            React.createElement('span', { className: 'onboarding-section-opt' }, ' · optional')
          ),
          React.createElement('p', { className: 'onboarding-section-desc' },
            'PRDs, user research, brand guidelines — anything that shapes who you serve.'
          ),
          React.createElement('input', {
            type: 'file', multiple: true,
            accept: '.pdf,.docx,.md,.txt,.csv,.png,.jpg,.jpeg',
            ref: contextInputRef, style: { display: 'none' },
            onChange: handleContextFiles
          }),
          React.createElement('div', { className: 'dropzone', onClick: () => contextInputRef.current.click() },
            React.createElement(IconUpload, null),
            React.createElement('strong', null, 'Upload context'),
            React.createElement('span', null, 'PDF, DOCX, MD, TXT')
          ),
          files.map(f =>
            React.createElement('div', { key: f.id, className: 'file-chip' },
              React.createElement(IconFile, null),
              React.createElement('span', { className: 'fname' }, f.name),
              React.createElement('span', { className: 'fsize' }, f.size),
              React.createElement('button', { className: 'chip-del', onClick: () => setFiles(fs => fs.filter(x => x.id !== f.id)) },
                React.createElement(IconX, { width: 9, height: 9 })
              )
            )
          )
        ),

        // CTA
        React.createElement('div', { className: 'onboarding-cta' },
          React.createElement('button', {
            className: 'onboarding-continue',
            onClick: canContinue ? onContinue : undefined,
            disabled: !canContinue
          }, 'Continue →')
        )
      )
    )
  );
}

window.Onboarding = Onboarding;

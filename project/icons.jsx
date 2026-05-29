/* global React */
const { createElement: h } = React;

// Icons — simple, inline SVGs
const icon = (path, props = {}) => (p) => h('svg', {
  viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75,
  strokeLinecap: 'round', strokeLinejoin: 'round', ...props, ...p
}, ...(Array.isArray(path) ? path : [path]).map((d, i) => h('path', { key: i, d })));

const IconLink = icon(['M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71', 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71']);
const IconImage = icon(['M3 5h18v14H3z', 'm3 15 5-5 4 4 3-3 6 6']);
const IconVideo = icon(['m22 8-6 4 6 4V8Z', 'M14 6H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2Z']);
const IconUpload = icon(['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm17 8-5-5-5 5', 'M12 3v12']);
const IconFile = icon(['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M16 13H8', 'M16 17H8', 'M10 9H8']);
const IconSend = icon(['m22 2-7 20-4-9-9-4 20-7Z']);
const IconMic = icon(['M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z', 'M19 10v2a7 7 0 0 1-14 0v-2', 'M12 19v3']);
const IconStar = icon('M12 2l2.9 6.9L22 10l-5.5 4.8L18 22l-6-3.6L6 22l1.5-7.2L2 10l7.1-1.1L12 2z');
const IconSparkle = icon(['M12 3v18', 'M3 12h18', 'm5.64 5.64 12.72 12.72', 'm18.36 5.64-12.72 12.72'], { strokeWidth: 1.25 });
const IconCheck = icon('m5 12 5 5L20 7');
const IconArrow = icon('m9 6 6 6-6 6');
const IconX = icon(['m18 6-12 12', 'm6 6 12 12']);
const IconCopy = icon(['M16 4H6a2 2 0 0 0-2 2v10', 'M20 8H10a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2Z']);
const IconTerminal = icon(['m4 7 6 6-6 6', 'M12 19h8']);
const IconSettings = icon(['M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z']);
const IconShare = icon(['M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8', 'm16 6-4-4-4 4', 'M12 2v13']);
const IconCoin = icon(['M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10Z', 'M8 14s1.5 2 4 2 4-2 4-2', 'M12 7v10']);
const IconSun = icon(['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z', 'M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42']);
const IconMoon = icon('M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z');
const IconBolt = icon('M13 2 3 14h9l-1 8 10-12h-9l1-8z');
const IconChat = icon('M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z');
const IconTarget = icon(['M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10Z', 'M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z', 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z']);
const IconFlask = icon(['M9 2v7l-6 12a2 2 0 0 0 1.7 3h14.6a2 2 0 0 0 1.7-3l-6-12V2', 'M7 2h10']);
const IconPlay = icon('M6 3v18l15-9z');
const IconPulse = icon('m3 12 4 0 3-9 4 18 3-9 4 0');

Object.assign(window, {
  IconLink, IconImage, IconVideo, IconUpload, IconFile, IconSend, IconMic,
  IconStar, IconSparkle, IconCheck, IconArrow, IconX, IconCopy, IconTerminal,
  IconSettings, IconShare, IconCoin, IconSun, IconMoon, IconBolt, IconChat,
  IconTarget, IconFlask, IconPlay, IconPulse
});

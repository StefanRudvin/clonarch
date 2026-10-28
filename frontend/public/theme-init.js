// Run before first paint. Kept external to respect the same-origin script CSP.
(function () {
  var theme = 'system';
  try { theme = localStorage.getItem('clonarch-theme') || 'system'; } catch (_) {}
  var dark = theme === 'dark' || (theme !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name="theme-color"]').setAttribute('content', dark ? '#18181b' : '#f5f7f4');
})();

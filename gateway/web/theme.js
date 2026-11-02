'use strict';
(() => {
  const designs = ['titan', 'paper', 'console', 'contour'];
  let theme, design;
  try { theme = localStorage.getItem('xray-theme'); design = localStorage.getItem('xray-design'); } catch {}
  if (!['light', 'dark'].includes(theme)) theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  if (!designs.includes(design)) design = 'titan';
  const apply = (notify = false) => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.design = design;
    const button = document.getElementById('themeToggle');
    if (button) {
      const text = theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему';
      button.setAttribute('aria-label', window.I18n ? window.I18n.t(text) : text);
    }
    document.querySelectorAll('#appearanceForm input[name="design"]').forEach(input => { input.checked = input.value === design; });
    document.querySelectorAll('#appearanceForm input[name="colorScheme"]').forEach(input => { input.checked = input.value === theme; });
    if (notify) document.dispatchEvent(new CustomEvent('appearancechange'));
  };
  const save = () => {
    try { localStorage.setItem('xray-theme', theme); localStorage.setItem('xray-design', design); } catch {}
    apply(true);
  };
  apply();
  document.addEventListener('languagechange', () => apply());
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('themeToggle').addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      save();
    });
    document.getElementById('appearanceForm').addEventListener('change', event => {
      const input = event.target;
      if (input.name === 'design' && designs.includes(input.value)) design = input.value;
      else if (input.name === 'colorScheme' && ['light', 'dark'].includes(input.value)) theme = input.value;
      else return;
      save();
    });
    document.getElementById('appearanceForm').addEventListener('submit', event => event.preventDefault());
  });
  window.addEventListener('storage', event => {
    if (event.key === 'xray-design') design = designs.includes(event.newValue) ? event.newValue : 'titan';
    else if (event.key === 'xray-theme') theme = ['light', 'dark'].includes(event.newValue) ? event.newValue : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    else return;
    apply(true);
  });
})();

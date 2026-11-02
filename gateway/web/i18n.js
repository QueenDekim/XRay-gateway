'use strict';
(() => {
  const messages = window.XrayMessages || {};
  const reverse = Object.fromEntries(Object.entries(messages).map(([source, target]) => [target, source]));
  const automatic = () => typeof navigator !== 'undefined' && navigator.language && !navigator.language.toLowerCase().startsWith('ru') ? 'en' : 'ru';
  let language;
  try { language = localStorage.getItem('xray-language'); } catch {}
  if (!['ru', 'en'].includes(language)) language = automatic();
  const t = (source, ...values) => {
    source = String(source ?? '');
    let result = language === 'en' ? (messages[source] ?? source) : (reverse[source] ?? source);
    if (result === source) {
      for (const [ru, en] of Object.entries(messages).filter(([key]) => key.endsWith(': ')).sort((a,b) => b[0].length-a[0].length)) {
        if (language === 'en' && source.startsWith(ru)) { result = en + source.slice(ru.length); break; }
        if (language === 'ru' && source.startsWith(en)) { result = ru + source.slice(en.length); break; }
      }
    }
    return values.length ? result.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match) : result;
  };
  const apply = () => {
    document.documentElement.lang = language;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll('[data-i18n-aria]').forEach(node => { node.setAttribute('aria-label', t(node.dataset.i18nAria)); });
    document.querySelectorAll('[data-language-select]').forEach(select => { select.value = language; });
    document.title = t('Xray Gateway — Управление');
  };
  const setLanguage = (value, persist = true) => {
    if (!['ru', 'en'].includes(value)) return;
    language = value;
    if (persist) { try { localStorage.setItem('xray-language', value); } catch {} }
    apply();
    document.dispatchEvent(new CustomEvent('languagechange'));
  };
  window.I18n = { t, apply, setLanguage, language: () => language, locale: () => language === 'ru' ? 'ru-RU' : 'en-US' };
  document.documentElement.lang = language;
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.querySelectorAll('[data-language-select]').forEach(select => select.addEventListener('change', () => setLanguage(select.value)));
  });
  window.addEventListener('storage', event => {
    if (event.key === 'xray-language') setLanguage(['ru', 'en'].includes(event.newValue) ? event.newValue : automatic(), false);
  });
})();

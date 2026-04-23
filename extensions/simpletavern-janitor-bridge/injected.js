(function injectXhrAndFetchBridge() {
  const CHANNEL = 'st-janitor-bridge';

  const isLikelyChatEndpoint = (url) => {
    if (typeof url !== 'string') return false;
    const clean = url.split('?')[0] || '';
    const parts = clean.split('/').filter(Boolean);
    const last = parts[parts.length - 1] || '';
    return /^[0-9]+$/.test(last);
  };

  const extractFetchUrl = (input) => {
    if (typeof input === 'string') return input;
    if (input && typeof input === 'object' && typeof input.url === 'string') return input.url;
    return '';
  };

  const postPayload = (type, data) => {
    window.postMessage({ source: CHANNEL, type, data }, '*');
  };

  const XHR = XMLHttpRequest.prototype;
  const origOpen = XHR.open;
  const origSend = XHR.send;

  XHR.open = function open(method, url) {
    this.__stUrl = url;
    return origOpen.apply(this, arguments);
  };

  XHR.send = function send() {
    this.addEventListener('load', function onLoad() {
      try {
        if (!isLikelyChatEndpoint(this.__stUrl)) return;
        if (!this.responseText) return;
        postPayload('xhr', this.responseText);
      } catch (_) {
        // noop
      }
    });
    return origSend.apply(this, arguments);
  };

  const origFetch = window.fetch;
  window.fetch = async function wrappedFetch(...args) {
    const resp = await origFetch(...args);
    const requestUrl = extractFetchUrl(args[0]);
    if (!isLikelyChatEndpoint(requestUrl)) {
      return resp;
    }
    try {
      const text = await resp.clone().text();
      if (!text || !text.trim()) return resp;
      const parsed = JSON.parse(text);
      postPayload('fetch', parsed);
    } catch (_) {
      // noop
    }
    return resp;
  };

  function extractJaiCharacterFromMbxM() {
    try {
      const arr = window.mbxM;
      if (!Array.isArray(arr)) return null;
      for (let i = 0; i < arr.length; i += 1) {
        const entry = arr[i];
        if (!entry || typeof entry !== 'object') continue;
        const storeKey = Object.keys(entry).find((k) => k.endsWith('characterStore'));
        if (!storeKey) continue;
        const ch = entry[storeKey] && entry[storeKey].character;
        if (ch && typeof ch === 'object' && (ch.first_message || (ch.first_messages && ch.first_messages.length))) {
          return ch;
        }
      }
    } catch (_e) {
      // noop
    }
    return null;
  }

  function postCharJson(charObj) {
    if (!charObj) return;
    try {
      window.postMessage({ source: CHANNEL, type: 'char-json', data: charObj }, '*');
    } catch (_e) {
      // noop
    }
  }

  function tryEmitCharJson() {
    const ch = extractJaiCharacterFromMbxM();
    if (ch) postCharJson(ch);
  }

  if (document.readyState === 'complete') {
    tryEmitCharJson();
  } else {
    window.addEventListener('load', function onJaiLoad() {
      tryEmitCharJson();
    });
  }
  setTimeout(tryEmitCharJson, 0);
  setTimeout(tryEmitCharJson, 500);
  setTimeout(tryEmitCharJson, 2000);
})();

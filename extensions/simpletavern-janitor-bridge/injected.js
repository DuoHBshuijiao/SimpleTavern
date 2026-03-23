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
})();

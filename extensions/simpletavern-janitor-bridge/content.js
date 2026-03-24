(function simpleTavernJanitorBridge() {
  const LOG_PREFIX = '[ST-JanitorBridge]';
  const CHANNEL = 'st-janitor-bridge';
  const ACTIVATE_PARAM = '_st_import';
  const APP_BASE_PARAM = '_st_app_base';
  const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
  const DEFAULT_APP_BASE = 'http://127.0.0.1:5173';
  const CHAR_HTML_PARAM = '_st_char_html';
  const state = {
    sent: false,
    sending: false,
    lastSignature: '',
    chatActivated: false,
    charHtmlActivated: false,
    appBaseHint: '',
  };

  function injectScript() {
    const src = chrome.runtime.getURL('injected.js');
    const script = document.createElement('script');
    script.src = src;
    script.onload = () => script.remove();
    (document.head || document.documentElement).appendChild(script);
  }

  function parseCandidate(raw) {
    try {
      if (typeof raw === 'string') return JSON.parse(raw);
      if (raw && typeof raw === 'object') return raw;
      return null;
    } catch {
      return null;
    }
  }

  function isValidPayload(payload) {
    return !!payload && Array.isArray(payload.chatMessages) && payload.chatMessages.length > 0;
  }

  function payloadSignature(payload) {
    const messages = payload.chatMessages || [];
    const first = messages[0] || {};
    const last = messages[messages.length - 1] || {};
    return `${messages.length}:${first.created_at || ''}:${last.created_at || ''}`;
  }

  function getConfig() {
    return new Promise((resolve) => {
      chrome.storage.sync.get(['apiBaseUrl', 'appBaseUrl'], (items) => {
        resolve({
          apiBaseUrl: (items.apiBaseUrl || DEFAULT_API_BASE).replace(/\/+$/, ''),
          appBaseUrl: (items.appBaseUrl || DEFAULT_APP_BASE).replace(/\/+$/, ''),
        });
      });
    });
  }

  function logInfo(...args) {
    console.info(LOG_PREFIX, ...args);
  }

  function logWarn(...args) {
    console.warn(LOG_PREFIX, ...args);
  }

  function resolveActivation() {
    try {
      const u = new URL(window.location.href);
      state.charHtmlActivated = u.searchParams.get(CHAR_HTML_PARAM) === '1';
      state.chatActivated = !state.charHtmlActivated && u.searchParams.get(ACTIVATE_PARAM) === '1';
      state.appBaseHint = (u.searchParams.get(APP_BASE_PARAM) || '').replace(/\/+$/, '');
      if (state.charHtmlActivated || state.chatActivated) {
        u.searchParams.delete(CHAR_HTML_PARAM);
        u.searchParams.delete(ACTIVATE_PARAM);
        u.searchParams.delete('_st_ts');
        u.searchParams.delete(APP_BASE_PARAM);
        history.replaceState(null, '', u.toString());
        if (state.charHtmlActivated) {
          logInfo('character HTML capture armed', state.appBaseHint ? `(appBase=${state.appBaseHint})` : '');
        } else {
          logInfo('chat capture armed for this page', state.appBaseHint ? `(appBase=${state.appBaseHint})` : '');
        }
      } else {
        logInfo('capture idle (no _st_import / _st_char_html)');
      }
    } catch (err) {
      state.chatActivated = false;
      state.charHtmlActivated = false;
      logWarn('failed to resolve activation', err);
    }
  }

  async function sendPending(payload) {
    if (!state.chatActivated) return;
    if (state.sent || state.sending) return;
    state.sending = true;
    try {
      const { apiBaseUrl, appBaseUrl } = await getConfig();
      const openBase = (state.appBaseHint || appBaseUrl || DEFAULT_APP_BASE).replace(/\/+$/, '');
      logInfo('posting pending to', `${apiBaseUrl}/api/import/janitor/pending`);
      const resp = await fetch(`${apiBaseUrl}/api/import/janitor/pending`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const result = await resp.json();
      const pendingId = result?.pendingId;
      if (!pendingId) {
        throw new Error('pendingId missing');
      }
      state.sent = true;
      state.chatActivated = false;
      const targetUrl = `${openBase}/chat?janitorPending=${encodeURIComponent(pendingId)}`;
      chrome.runtime.sendMessage({ type: 'open-simpletavern', url: targetUrl }, () => {
        if (chrome.runtime.lastError) {
          logWarn('open-simpletavern message failed', chrome.runtime.lastError.message);
          return;
        }
        logInfo('pending posted, requested app open');
      });
    } catch (err) {
      // 网络或配置失败时保持可重试（刷新后再次自动尝试）
      state.sent = false;
      logWarn('send pending failed', err);
    } finally {
      state.sending = false;
    }
  }

  async function sendCharacterHtml() {
    if (!state.charHtmlActivated) return;
    if (state.sent || state.sending) return;
    state.sending = true;
    try {
      const { apiBaseUrl, appBaseUrl } = await getConfig();
      const openBase = (state.appBaseHint || appBaseUrl || DEFAULT_APP_BASE).replace(/\/+$/, '');
      const html = document.documentElement.outerHTML;
      if (!html || html.length < 200) {
        throw new Error('页面 HTML 过短，可能尚未加载完成，请稍后重试');
      }
      logInfo('posting character page HTML to', `${apiBaseUrl}/api/import/janitor/character-html`);
      const resp = await fetch(`${apiBaseUrl}/api/import/janitor/character-html`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html }),
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      const result = await resp.json();
      const characterId = result?.characterId;
      const characterName = result?.characterName || '';
      const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
      state.sent = true;
      state.charHtmlActivated = false;
      const q = new URLSearchParams();
      q.set('janitorCharImport', '1');
      if (characterId) q.set('janitorCharId', String(characterId));
      if (characterName) q.set('janitorCharName', characterName);
      if (warnings.length) {
        try {
          q.set('janitorCharWarnings', JSON.stringify(warnings));
        } catch (_) {
          // ignore oversized / invalid
        }
      }
      const targetUrl = `${openBase}/chat?${q.toString()}`;
      chrome.runtime.sendMessage({ type: 'open-simpletavern', url: targetUrl }, () => {
        if (chrome.runtime.lastError) {
          logWarn('open-simpletavern message failed', chrome.runtime.lastError.message);
          return;
        }
        logInfo('character imported, requested app open');
      });
    } catch (err) {
      state.sent = false;
      logWarn('send character html failed', err);
    } finally {
      state.sending = false;
    }
  }

  function scheduleCharacterHtmlCapture() {
    if (!state.charHtmlActivated) return;
    const delayMs = 2500;
    const run = () => {
      void sendCharacterHtml();
    };
    if (document.readyState === 'complete') {
      window.setTimeout(run, delayMs);
    } else {
      window.addEventListener('load', () => window.setTimeout(run, delayMs), { once: true });
    }
  }

  window.addEventListener('message', (event) => {
    if (!state.chatActivated) return;
    const data = event.data;
    if (!data || data.source !== CHANNEL) return;
    const payload = parseCandidate(data.data);
    if (!isValidPayload(payload)) return;
    const signature = payloadSignature(payload);
    if (state.lastSignature === signature || state.sent) return;
    state.lastSignature = signature;
    logInfo('first valid payload captured, auto posting');
    void sendPending(payload);
  });

  resolveActivation();
  if (state.chatActivated) {
    injectScript();
  }
  if (state.charHtmlActivated) {
    scheduleCharacterHtmlCapture();
  }
})();

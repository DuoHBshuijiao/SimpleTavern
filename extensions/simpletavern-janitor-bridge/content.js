(function simpleTavernJanitorBridge() {
  const LOG_PREFIX = '[ST-JanitorBridge]';
  const CHANNEL = 'st-janitor-bridge';
  const ACTIVATE_PARAM = '_st_import';
  const APP_BASE_PARAM = '_st_app_base';
  const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
  const DEFAULT_APP_BASE = 'http://127.0.0.1:5173';
  const state = {
    sent: false,
    sending: false,
    lastSignature: '',
    activated: false,
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
      state.activated = u.searchParams.get(ACTIVATE_PARAM) === '1';
      state.appBaseHint = (u.searchParams.get(APP_BASE_PARAM) || '').replace(/\/+$/, '');
      if (state.activated) {
        // 清理 URL 标记，避免用户刷新后重复触发
        u.searchParams.delete(ACTIVATE_PARAM);
        u.searchParams.delete('_st_ts');
        u.searchParams.delete(APP_BASE_PARAM);
        history.replaceState(null, '', u.toString());
        logInfo('capture armed for this page', state.appBaseHint ? `(appBase=${state.appBaseHint})` : '');
      } else {
        logInfo('capture idle (no _st_import=1)');
      }
    } catch (err) {
      state.activated = false;
      logWarn('failed to resolve activation', err);
    }
  }

  async function sendPending(payload) {
    if (!state.activated) return;
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
      state.activated = false;
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

  window.addEventListener('message', (event) => {
    if (!state.activated) return;
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
  injectScript();
})();

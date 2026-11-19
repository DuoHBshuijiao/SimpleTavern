/**
 * 若当前标签页 URL 仍带有 janitorPending，则合并到目标 URL（避免角色导入回跳时丢失聊天暂存 id）。
 */
function mergeJanitorPendingFromTab(currentUrl, destUrl) {
  try {
    const cur = new URL(currentUrl);
    const pend = cur.searchParams.get('janitorPending');
    if (!pend) return destUrl;
    const dest = new URL(destUrl);
    if (!dest.searchParams.has('janitorPending')) {
      dest.searchParams.set('janitorPending', pend);
    }
    return dest.toString();
  } catch {
    return destUrl;
  }
}

const importKinds = new Set(['pending', 'character-json', 'character-html']);

async function postJanitorImport(message, sender) {
  const page = new URL(sender.url);
  if (page.protocol !== 'https:' || (page.hostname !== 'janitorai.com' && !page.hostname.endsWith('.janitorai.com'))) {
    throw new Error('JanitorAI import must originate from a JanitorAI tab');
  }
  if (!importKinds.has(message.kind)) throw new Error('Unknown import type');

  const target = new URL(message.apiBaseUrl);
  if (!['http:', 'https:'].includes(target.protocol) || !['127.0.0.1', 'localhost'].includes(target.hostname)
      || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
    throw new Error('SimpleTavern import needs a local HTTP address');
  }
  const response = await fetch(new URL(`/api/import/janitor/${message.kind}`, target), {
    method: 'POST',
    credentials: 'omit',
    redirect: 'error',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(message.payload),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = result?.detail?.message ?? result?.detail ?? result?.message;
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`);
  }
  if (!result?.ok) throw new Error('SimpleTavern did not return an import result');
  return result;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.info('[ST-JanitorBridge:bg] message', message?.type || 'unknown');
  if (message?.type === 'post-janitor-import') {
    postJanitorImport(message, sender).then(
      (result) => sendResponse({ ok: true, result }),
      (error) => sendResponse({ ok: false, error: error.message }),
    );
    return true;
  }
  if (!message || message.type !== 'open-simpletavern' || typeof message.url !== 'string') {
    return false;
  }

  const targetUrl = message.url;
  let pattern = targetUrl;
  try {
    const parsed = new URL(targetUrl);
    pattern = `${parsed.origin}/chat*`;
  } catch {
    // use raw targetUrl fallback
  }

  chrome.tabs.query({ url: [pattern] }, (tabs) => {
    if (chrome.runtime.lastError) {
      console.warn('[ST-JanitorBridge:bg] tabs.query failed', chrome.runtime.lastError.message);
    }
    const first = tabs && tabs.length > 0 ? tabs[0] : null;
    if (first && typeof first.id === 'number') {
      const urlToOpen = first.url ? mergeJanitorPendingFromTab(first.url, targetUrl) : targetUrl;
      chrome.tabs.update(first.id, { url: urlToOpen, active: true }, () => {
        if (chrome.runtime.lastError) {
          console.warn('[ST-JanitorBridge:bg] tabs.update failed', chrome.runtime.lastError.message);
        }
        if (first.windowId != null) {
          chrome.windows.update(first.windowId, { focused: true });
        }
        console.info('[ST-JanitorBridge:bg] updated existing tab');
        sendResponse({ ok: true, mode: 'update' });
      });
      return;
    }

    chrome.tabs.create({ url: targetUrl, active: true }, () => {
      if (chrome.runtime.lastError) {
        console.warn('[ST-JanitorBridge:bg] tabs.create failed', chrome.runtime.lastError.message);
      } else {
        console.info('[ST-JanitorBridge:bg] created new tab');
      }
      sendResponse({ ok: true, mode: 'create' });
    });
  });

  return true;
});

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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  console.info('[ST-JanitorBridge:bg] message', message?.type || 'unknown');
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

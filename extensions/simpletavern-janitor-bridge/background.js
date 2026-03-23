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
      chrome.tabs.update(first.id, { url: targetUrl, active: true }, () => {
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

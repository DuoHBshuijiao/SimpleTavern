/** 在 SimpleTavern 应用页注入页面上下文标记，供前端检测扩展是否已安装（content script 与页面 JS 隔离）。使用外链脚本以符合页面 CSP（避免内联脚本）。 */
(function stJanitorBridgeAppMark() {
  try {
    const el = document.createElement('script');
    el.src = chrome.runtime.getURL('page-mark.js');
    el.onload = () => el.remove();
    el.onerror = () => el.remove();
    (document.documentElement || document.head).appendChild(el);
  } catch (_) {
    /* noop */
  }
})();

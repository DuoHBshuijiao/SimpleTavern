/** 在 SimpleTavern 应用页注入页面上下文标记，供前端检测扩展是否已安装（content script 与页面 JS 隔离）。 */
(function stJanitorBridgeAppMark() {
  try {
    const el = document.createElement('script');
    el.textContent = 'window.__ST_JANITOR_BRIDGE_INSTALLED__ = true;';
    (document.documentElement || document.head).appendChild(el);
    el.remove();
  } catch (_) {
    /* noop */
  }
})();

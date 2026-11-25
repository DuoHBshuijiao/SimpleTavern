window.__ST_JANITOR_BRIDGE_INSTALLED__ = true;
window.__ST_JANITOR_BRIDGE_VERSION__ = document.currentScript?.dataset.bridgeVersion;
window.dispatchEvent(new Event('simpletavern:janitor-bridge-ready'));

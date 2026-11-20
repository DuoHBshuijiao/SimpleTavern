"""Service-manager view of configured local TTS presets, sent on the private pipe."""
import asyncio

from app.routes import tts
from app.services import glm_local_tts_process as glm, omnivoice_local_tts_process as omni
from app.services import qwen3_local_tts_process as qwen
from app.storage import load_settings


def _engines():
    return {
        "glm_local": (glm, "Glm", 8088, tts.glm_local_start, tts.GlmLocalStartReq),
        "qwen3_local": (qwen, "Qwen3", 8080, tts.qwen3_local_start, tts.Qwen3LocalStartReq),
        "omnivoice_local": (omni, "OmniVoice", 8089, tts.omnivoice_local_start, tts.OmniVoiceLocalStartReq),
    }


async def handle(command, emit):
    settings = await asyncio.to_thread(load_settings)
    presets = [p for p in settings.apiPresets if settings.ttsEnabled and p.presetKind == "tts"
               and p.ttsProvider in _engines()]
    rows = []
    for preset in presets:
        module, label, default_port, start, req = _engines()[preset.ttsProvider]
        prefix = f"tts{label}Local"
        managed = getattr(preset, prefix + "Managed")
        port = getattr(preset, prefix + "Port") or default_port
        ports = [port]
        if module is qwen:
            ports.append(tts._qwen3_voice_clone_port(preset))
        owned = any(module.owns_port(p) for p in ports)
        state = "owned" if owned else "idle" if managed else "external"
        if command.get("id") == preset.id:
            op = command.get("op")
            if op == "start" and managed:
                result = await start(req(preset_id=preset.id))
                if not result["ok"]:
                    raise RuntimeError("启动失败")
                state = "owned" if any(module.owns_port(p) for p in ports) else "external_ready"
            elif op == "stop" and managed and owned:
                for p in ports:
                    if module.owns_port(p):
                        await asyncio.to_thread(module.stop_port, p)
                state = "idle"
            elif op == "health":
                platform = tts._get_platform(settings, preset.id)
                try:
                    reachable = await platform.health_check()
                    state = ("owned" if owned else "external_ready") if reachable else "unreachable"
                finally:
                    await platform.close()
            emit("voice_result", op=op, state=state)
        rows.append({"id": preset.id, "name": preset.name, "provider": label, "state": state,
                     "managed": managed, "owned": managed and any(module.owns_port(p) for p in ports)})
    emit("voices", rows=rows)

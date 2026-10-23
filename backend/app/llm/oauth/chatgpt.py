"""Official Sign in with ChatGPT public-client registration and inference profile."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

from app.llm.oauth.http import request_json
from app.llm.oauth.store import load_token, save_token
from app import storage

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
MANAGE_URL = "https://chatgpt.com/settings/usage"


class InvalidRefreshToken(ValueError):
    pass


def host_id() -> str:
    path = storage._data_dir() / "oauth_host.json"
    try:
        value = storage.read_json(path).get("hostId")
    except FileNotFoundError:
        value = None
    if not value:
        value = "urn:uuid:" + str(uuid.uuid4())
        storage.write_json(path, {"hostId": value})
    return value


async def validate_identity(token: str, client_id: str, nonce: str | None = None) -> dict:
    import jwt
    status, jwks, _ = await request_json("GET", ISSUER + "/.well-known/jwks.json")
    if status != 200 or not isinstance(jwks, dict):
        raise ValueError("无法获取 OpenAI 身份验证公钥")
    header = jwt.get_unverified_header(token)
    if header.get("alg") not in {"RS256", "ES256"}:
        raise ValueError("不支持的 ID token 签名算法")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise ValueError("ID token 公钥不存在")
    claims = jwt.decode(token, jwt.PyJWK.from_dict(key).key, algorithms=[header["alg"]], audience=client_id,
                        issuer=ISSUER, leeway=5, options={"require": ["sub", "exp", "iat"]})
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ValueError("ID token 缺少账号身份")
    if nonce is not None and not secrets.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise ValueError("ID token nonce 不匹配")
    return claims


async def token_record(data: dict, *, client_id: str, prior: dict | None = None, nonce: str | None = None) -> dict:
    prior = prior or {}
    identity = await validate_identity(str(data.get("id_token") or ""), client_id, nonce) if data.get("id_token") else None
    if nonce is not None and identity is None:
        raise ValueError("登录响应缺少 ID token")
    if identity and prior.get("subject") and identity["sub"] != prior["subject"]:
        raise ValueError("登录账号与选中的注册不一致")
    scopes = str(data.get("scope") or " ".join(prior.get("scopes") or [])).split()
    if str(data.get("token_type", "Bearer")).lower() != "bearer" or not data.get("access_token"):
        raise ValueError("OAuth 响应缺少有效 Bearer 令牌")
    return {**prior, "provider": "openai-chatgpt", "clientId": client_id, "hostId": host_id(),
            "subject": identity["sub"] if identity else prior.get("subject"),
            "accountId": identity["sub"] if identity else prior.get("accountId"),
            "email": identity.get("email") if identity else prior.get("email"), "issuer": ISSUER,
            "idToken": data.get("id_token") or prior.get("idToken"), "scopes": scopes,
            "accessToken": data["access_token"], "refreshToken": data.get("refresh_token") or prior.get("refreshToken"),
            "expiresAt": int(time.time() * 1000) + int(data.get("expires_in", 3600)) * 1000}


async def refresh_record(record: dict) -> dict:
    status, data, _ = await request_json("POST", TOKEN_URL, data={"grant_type": "refresh_token",
        "client_id": record["clientId"], "refresh_token": record["refreshToken"], "resource": RESOURCE})
    if status != 200 or not isinstance(data, dict):
        code = data.get("error") if isinstance(data, dict) else "refresh_failed"
        error = InvalidRefreshToken if code in {"invalid_grant", "invalid_refresh_token", "token_expired",
            "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"} else ValueError
        raise error("OpenAI 刷新失败，请重新登录" if error is InvalidRefreshToken else "OpenAI 刷新暂时失败，请稍后重试")
    return await token_record(data, client_id=record["clientId"], prior=record)


async def start_loopback(session) -> dict:
    prior = load_token(session.preset_id) or {}
    if prior.get("provider") != "openai-chatgpt":
        prior = {}
    verifier, state, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    session.extra.update({"status": "pending", "prior": prior})
    async def callback(reader, writer):
        message = "登录回调无效，请返回应用重新登录。"
        accepted = False
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            target = raw.decode("ascii").split(" ")[1]
            parsed = urlsplit(target)
            query = parse_qs(parsed.query)
            get = lambda key: (query.get(key) or [""])[0]
            if parsed.path != "/auth/callback" or not secrets.compare_digest(get("state"), state):
                raise ValueError("OAuth state 不匹配")
            if session.extra.get("consumed"):
                raise ValueError("登录回调已使用")
            session.extra["consumed"] = True
            accepted = True
            if get("error"):
                raise ValueError("用户拒绝或取消授权")
            client_id = prior.get("clientId") or get("client_id")
            if not client_id or client_id == "dynamic_agent_client" or (prior.get("clientId") and get("client_id") not in {"", client_id}):
                raise ValueError("OAuth 注册 client_id 无效")
            if session.extra.get("cancelled") or session.expires_at <= time.time():
                raise ValueError("登录会话已取消或过期")
            # Dynamic registration survives an expired code or a failed exchange.
            # Do not replace the active account's credentials during reauthorization.
            if not prior.get("clientId"):
                save_token(session.preset_id, {"provider": "openai-chatgpt", "clientId": client_id, "hostId": host_id()})
            status, data, _ = await request_json("POST", TOKEN_URL, data={"grant_type": "authorization_code",
                "client_id": client_id, "code": get("code"), "code_verifier": verifier,
                "redirect_uri": session.extra["redirectUri"], "resource": RESOURCE})
            if status != 200 or not isinstance(data, dict):
                raise ValueError("OpenAI 授权码兑换失败，请重新登录")
            record = await token_record(data, client_id=client_id, prior=prior, nonce=nonce)
            if session.extra.get("cancelled") or session.expires_at <= time.time():
                raise ValueError("登录会话已取消或过期")
            settings = storage.load_settings()
            current = next((p for p in settings.apiPresets if p.id == session.preset_id), None)
            if current is None or current.providerId != "openai-chatgpt":
                raise ValueError("登录期间预设已删除或更换供应商")
            save_token(session.preset_id, record)
            session.extra["status"] = "complete"
            message = "登录成功，可以关闭此页并返回 SimpleTavern。"
        except Exception as exc:
            # Never expose callback URLs, tokens, or upstream response bodies.
            if accepted:
                session.extra.update(status="failed", message=str(exc) if isinstance(exc, ValueError) else "登录验证失败，请重试")
        body = message.encode("utf-8")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        if session.extra.get("consumed"):
            session.extra["listener"].close()
    server = await asyncio.start_server(callback, "127.0.0.1", 0, limit=16384)
    uri = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/auth/callback"
    session.extra.update(listener=server, redirectUri=uri)
    params = {"client_id": prior.get("clientId") or "dynamic_agent_client", "ext_agent_host_id": host_id(),
        "response_type": "code", "redirect_uri": uri, "scope": SCOPES, "resource": RESOURCE,
        "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    if prior.get("clientId"):
        # This URL crosses the UI bridge: do not expose a saved identity token in it.
        if prior.get("email"):
            params["login_hint"] = prior["email"]
    else:
        params["agent_name_hint"] = "SimpleTavern"
    return {"authorizeUrl": ISSUER + "/api/accounts/authorize?" + urlencode(params), "redirectUri": uri}


async def revoke(record: dict) -> bool:
    if not record.get("refreshToken"):
        return True
    try:
        status, config, _ = await request_json("GET", ISSUER + "/.well-known/openid-configuration")
        endpoint = config.get("revocation_endpoint") if status == 200 and isinstance(config, dict) else None
        if not endpoint or urlsplit(endpoint).netloc != "auth.openai.com" or not endpoint.startswith("https://"):
            return False
        status, _, _ = await request_json("POST", endpoint, data={"token": record["refreshToken"],
            "token_type_hint": "refresh_token", "client_id": record["clientId"]})
        return status == 200
    except Exception:
        return False

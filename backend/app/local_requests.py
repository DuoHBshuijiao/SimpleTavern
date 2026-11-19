from __future__ import annotations

import re
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_ORIGIN = r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?"
EXTENSION_ORIGIN = r"chrome-extension://[a-p]{32}"
CORS_ORIGIN_PATTERN = rf"(?:{LOCAL_ORIGIN}|{EXTENSION_ORIGIN})"
EXTENSION_IMPORT_PATHS = {
    "/api/import/janitor/pending",
    "/api/import/janitor/character-json",
    "/api/import/janitor/character-html",
}


class LocalRequestMiddleware:
    def __init__(self, app: ASGIApp, *, origins: list[str]) -> None:
        self.app = app
        self.origins = frozenset(origins)
        self.hosts = LOCAL_HOSTS | {urlsplit(origin).hostname for origin in origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        try:
            host = urlsplit("//" + hosts[0]) if len(hosts) == 1 else None
            valid_host = bool(host and host.hostname in self.hosts and not (
                host.username or host.password or host.path or host.query or host.fragment
            ))
        except ValueError:
            valid_host = False
        if not valid_host:
            await JSONResponse({"detail": "Host is not allowed"}, status_code=400)(scope, receive, send)
            return

        origins = headers.getlist("origin")
        if origins:
            origin = origins[0]
            extension_import = (
                bool(re.fullmatch(EXTENSION_ORIGIN, origin))
                and scope["method"] in {"POST", "OPTIONS"}
                and scope["path"] in EXTENSION_IMPORT_PATHS
            )
            if len(origins) != 1 or not (origin in self.origins or re.fullmatch(LOCAL_ORIGIN, origin) or extension_import):
                await JSONResponse({"detail": "Origin is not allowed"}, status_code=403)(scope, receive, send)
                return

        await self.app(scope, receive, send)

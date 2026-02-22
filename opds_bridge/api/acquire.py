from urllib.parse import quote
import re
from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from opds_bridge.security.basic import basic_auth_guard
from opds_bridge.services.abs_client import stream_download

router = APIRouter()

@router.get("/acquire/{item_id}")
@router.get("/acquire/{item_id}/{slug}")
def acquire(item_id: str,
            request: Request,
            slug: str | None = None,
            _=Depends(basic_auth_guard)):
    headers = {}
    rng = request.headers.get("range")
    if rng:
        headers["Range"] = rng

    r, body_iter = stream_download(item_id, headers=headers)

    if slug:
        filename_raw = slug
    else:
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?("?)([^";]+)\1', cd)
        filename_raw = m.group(2) if m else f"{item_id}.bin"

    filename_enc = quote(filename_raw)
    dispo = f"attachment; filename*=UTF-8''{filename_enc}"

    resp = StreamingResponse(body_iter,
                             media_type=r.headers.get("Content-Type", "application/octet-stream"),
                             status_code=r.status_code)
    for h in ("Content-Length", "Accept-Ranges", "Content-Range"):
        if r.headers.get(h):
            resp.headers[h] = r.headers[h]
    resp.headers["Content-Disposition"] = dispo
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp

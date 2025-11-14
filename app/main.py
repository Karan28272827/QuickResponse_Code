# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.models import Coin, Certificate
from app.supabase_client import supabase
from app.utils import sha256_from_bytes
import aiofiles
import os
from nanoid import generate
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Silver Coin QR Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # or ["*"] for quick dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@app.post("/api/admin/coins")
async def create_coin(serial: str | None = None, weight: float | None = None, purity: float | None = None, db=Depends(get_db)):
    # create coin record with short_id
    short_id = generate(size=10)  # nanoid
    coin = Coin(serial=serial, short_id=short_id, weight=weight, purity=purity)
    db.add(coin)
    await db.commit()
    await db.refresh(coin)
    return {"id": str(coin.id), "short_id": coin.short_id}

@app.post("/api/admin/coins/{short_id}/upload_cert")
async def upload_certificate(short_id: str, file: UploadFile = File(...), issued_by: str | None = None, db=Depends(get_db)):
    # find coin
    q = await db.execute(select(Coin).where(Coin.short_id == short_id))
    coin = q.scalar_one_or_none()
    if not coin:
        raise HTTPException(status_code=404, detail="coin not found")

    contents = await file.read()
    file_hash = sha256_from_bytes(contents)
    filename = file.filename
    storage_path = f"{short_id}/{filename}"  # path inside the 'certificates' bucket

    # Attempt upload
    try:
        res = supabase.storage.from_('certificates').upload(storage_path, contents, {"content-type": file.content_type})
    except Exception as exc:
        # log for debugging and return a JSON error
        print("Exception while uploading to Supabase:", repr(exc))
        # traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Storage client exception: {str(exc)}")

    # Debug print so you can see what the client returned
    print("Supabase upload response:", repr(res))

    # Handle dict-like responses
    if isinstance(res, dict):
        # older clients return dicts with "error" / "statusCode"
        if res.get("error") or (res.get("statusCode") and int(res.get("statusCode", 200)) >= 400):
            print("Supabase returned error dict:", res)
            raise HTTPException(status_code=500, detail=f"Supabase storage error: {res.get('error') or res.get('message')}")
        # success case -> continue

    else:
        # Handle object-like responses (UploadResponse)
        # Typical UploadResponse contains attributes like: path, full_path, etc.
        # If the object has an 'error' or 'status_code' attribute indicating failure, treat as error.
        if hasattr(res, "error") and getattr(res, "error"):
            print("Supabase upload object has error attr:", getattr(res, "error"))
            raise HTTPException(status_code=500, detail=f"Supabase storage error: {getattr(res, 'error')}")
        # You can optionally check status_code
        if hasattr(res, "status_code") and getattr(res, "status_code") and int(getattr(res, "status_code")) >= 400:
            raise HTTPException(status_code=500, detail=f"Supabase storage status {getattr(res, 'status_code')}")
        # If it has a path/full_path attribute we treat as success
        if not (hasattr(res, "path") or hasattr(res, "full_path") or hasattr(res, "fullPath")):
            # Unexpected shape — log and fail safely
            print("Unexpected Supabase upload response shape:", type(res), dir(res))
            raise HTTPException(status_code=500, detail="Unexpected response from storage client")

    # Record in DB
    try:
        cert = Certificate(coin_id=coin.id, storage_path=storage_path, file_hash=file_hash, issued_by=issued_by)
        db.add(cert)
        await db.commit()
        await db.refresh(cert)
    except Exception as exc:
        print("DB error saving certificate:", repr(exc))
        # traceback.print_exc()
        # Optionally: delete file from storage if DB save fails (left as an exercise)
        raise HTTPException(status_code=500, detail="Failed to save certificate record in DB")

    # Try to generate a short-lived signed URL for immediate testing (best-effort)
    signed_url = None
    try:
        signed_resp = supabase.storage.from_('certificates').create_signed_url(storage_path, 60)
        # signed_resp can be dict-like or object-like
        if isinstance(signed_resp, dict):
            signed_url = signed_resp.get("signedURL") or signed_resp.get("signed_url") or signed_resp.get("signedUrl")
        else:
            # try attributes
            signed_url = getattr(signed_resp, "signedURL", None) or getattr(signed_resp, "signed_url", None)
    except Exception as exc:
        print("Warning: failed to create signed URL:", repr(exc))

    return {"cert_id": str(cert.id), "storage_path": storage_path, "file_hash": file_hash, "signed_url": signed_url}

@app.get("/api/coins/{short_id}")
async def get_coin(short_id: str, db=Depends(get_db)):
    q = await db.execute(select(Coin).where(Coin.short_id == short_id))
    coin = q.scalar_one_or_none()
    if not coin:
        raise HTTPException(status_code=404, detail="Not found")
    # load certificates
    q2 = await db.execute(select(Certificate).where(Certificate.coin_id == coin.id))
    certs = q2.scalars().all()
    # generate signed url for each certificate (expires in 60s or configurable)
    signed = []
    for c in certs:
        url_data = supabase.storage.from_('certificates').create_signed_url(c.storage_path, 60)  # seconds
        signed.append({"id": str(c.id), "signed_url": url_data.get("signedURL"), "file_hash": c.file_hash, "issued_by": c.issued_by})
    return {
        "id": str(coin.id),
        "short_id": coin.short_id,
        "serial": coin.serial,
        "weight": float(coin.weight) if coin.weight is not None else None,
        "purity": float(coin.purity) if coin.purity is not None else None,
        "certificates": signed
    }

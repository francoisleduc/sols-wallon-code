"""Téléchargements avec cache local et journal de provenance (URL, date, empreinte SHA-256)."""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import RAW

PROVENANCE = RAW / "PROVENANCE.json"
USER_AGENT = "artificialisation-sol-be/1.0 (etude reproductible)"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(path: Path, url: str, note: str = "") -> None:
    log = json.loads(PROVENANCE.read_text(encoding="utf-8")) if PROVENANCE.exists() else {}
    log[path.relative_to(RAW).as_posix()] = {
        "url": url,
        "telecharge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "octets": path.stat().st_size,
        "sha256": _sha256(path),
        "note": note,
    }
    PROVENANCE.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch(url: str, dest: Path, refresh: bool = False, note: str = "") -> Path:
    """Télécharge `url` vers `dest` sauf si le fichier existe déjà (et `refresh` est faux)."""
    if dest.exists() and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    record(dest, url, note)
    return dest


def fetch_json(url: str, dest: Path, refresh: bool = False, note: str = "") -> dict:
    return json.loads(fetch(url, dest, refresh, note).read_text(encoding="utf-8"))

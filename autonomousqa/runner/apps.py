"""Sample-app manifests and server lifecycle.

Each app under apps/ is a frozen, stdlib-only product with an app.json
manifest describing how to serve it, its drive modality, its seeded corpus,
and the graded expectations for every capability. The harness treats the
manifest as data — no app-specific branches anywhere else.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

APPS_ROOT = Path(__file__).resolve().parent.parent / "apps"

MODALITIES = ("browser", "api", "cli", "extension")
TIERS = ("easy", "medium", "hard", "ambiguous")
EXPECTATIONS = ("verifiable", "unverifiable")


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    tier: str
    expected: str
    negative: bool


@dataclass(frozen=True)
class AppManifest:
    name: str
    dir: Path
    modality: str
    summary: str
    frozen: str
    serve: list[str]
    ready_path: str
    start_path: str
    corpus: Path
    capabilities: list[CapabilitySpec]
    extension_dir: Path | None = None

    def capability(self, capability_id: str) -> CapabilitySpec:
        for cap in self.capabilities:
            if cap.id == capability_id:
                return cap
        known = ", ".join(c.id for c in self.capabilities)
        raise KeyError(f"unknown capability '{capability_id}' for {self.name} (known: {known})")

    def flow_path(self, capability_id: str) -> Path:
        return self.dir / "flows" / f"{capability_id}.json"


def load_manifest(app_dir: Path) -> AppManifest:
    raw = json.loads((app_dir / "app.json").read_text())
    if raw["modality"] not in MODALITIES:
        raise ValueError(f"{app_dir}: unknown modality '{raw['modality']}'")
    capabilities = []
    for cap in raw["capabilities"]:
        if cap["tier"] not in TIERS:
            raise ValueError(f"{app_dir}: unknown tier '{cap['tier']}' on {cap['id']}")
        if cap["expected"] not in EXPECTATIONS:
            raise ValueError(f"{app_dir}: unknown expectation '{cap['expected']}' on {cap['id']}")
        capabilities.append(CapabilitySpec(
            id=cap["id"], tier=cap["tier"], expected=cap["expected"],
            negative=bool(cap["negative"]),
        ))
    extension_dir = app_dir / raw["extension_dir"] if "extension_dir" in raw else None
    if raw["modality"] == "extension" and extension_dir is None:
        raise ValueError(f"{app_dir}: extension modality needs extension_dir")
    return AppManifest(
        name=raw["name"],
        dir=app_dir,
        modality=raw["modality"],
        summary=raw["summary"],
        frozen=raw["frozen"],
        serve=list(raw["serve"]),
        ready_path=raw["ready_path"],
        start_path=raw["start_path"],
        corpus=app_dir / raw["corpus"],
        capabilities=capabilities,
        extension_dir=extension_dir,
    )


def list_apps(apps_root: Path = APPS_ROOT) -> list[AppManifest]:
    return [load_manifest(d) for d in sorted(apps_root.iterdir())
            if (d / "app.json").is_file()]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AppServer:
    """One running sample-app process bound to a fresh local port."""

    def __init__(self, manifest: AppManifest, port: int | None = None):
        self.manifest = manifest
        self.port = port or free_port()
        self.process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def start_url(self) -> str:
        return self.base_url + self.manifest.start_path

    def start(self, timeout: float = 15.0) -> None:
        argv = [arg.replace("{port}", str(self.port)) for arg in self.manifest.serve]
        if argv[0] == "python3":
            argv[0] = sys.executable
        self.process = subprocess.Popen(argv, cwd=self.manifest.dir)
        ready_url = self.base_url + self.manifest.ready_path
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.manifest.name} exited before becoming ready")
            try:
                with urllib.request.urlopen(ready_url, timeout=1):
                    return
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        self.stop()
        raise TimeoutError(f"{self.manifest.name} not ready at {ready_url} within {timeout}s")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None

    def __enter__(self) -> "AppServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

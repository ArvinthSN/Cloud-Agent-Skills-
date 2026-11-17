from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scan_repository import scan_repository
from analyze_architecture import analyze

EXAMPLES = ROOT / "examples"


def test_scan_fastapi():
    r = scan_repository(EXAMPLES / "python-fastapi")
    assert "python" in r.languages
    assert "fastapi" in r.frameworks
    assert r.has_dockerfile


def test_scan_nodejs():
    r = scan_repository(EXAMPLES / "nodejs-webapp")
    assert "javascript" in r.languages
    assert r.has_dockerfile


def test_scan_microservices():
    r = scan_repository(EXAMPLES / "microservices")
    assert r.has_docker_compose


def test_arch_monolith():
    r = scan_repository(EXAMPLES / "python-fastapi")
    a = analyze(r.to_dict())
    assert a.architecture in ("monolithic", "hybrid")
    assert a.confidence >= 0.3


def test_arch_microservices():
    r = scan_repository(EXAMPLES / "microservices")
    a = analyze(r.to_dict())
    assert a.architecture in ("microservices", "hybrid", "monolithic")
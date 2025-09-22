from __future__ import annotations
from miney.helper import doc


def test_doc_opens_browser(monkeypatch):
    calls = []

    def fake_open(url: str) -> bool:
        calls.append(url)
        return True

    monkeypatch.setattr("miney.helper.webbrowser.open", fake_open)
    doc(None)
    assert calls == ["https://miney.readthedocs.io/en/latest/"]

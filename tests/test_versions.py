"""Slice 18 (issue #30): a page per version.

site.build(posts, out), as in slice 8, with these changes for each published post:

- <out>/<slug>/index.html is site.render(post.md text, the records up to and including the last
  "published" record): records after the last publish are a draft and are not shown.
- For each "published" record, version N: <out>/<slug>/vN/index.html is site.render(post.md
  text, the records up to and including that record). If the folder <out>/<slug>/vN already
  exists, it is left exactly as it is: an old version is never rewritten.
"""

import json
from pathlib import Path

from ledger.site import build, render

POST = "---\ntitle: Rivers\n---\nText.\n"


def x(id, minute):
    return {"type": "exchange", "id": id, "at": f"2026-11-12T09:{minute:02d}:00Z", "source": "claude-code",
            "model": "claude-opus-5-5", "prompt": "P" + id, "reply": "R", "tools": []}


def snap(after, text):
    return {"type": "snapshot", "by": "ai", "after": after, "text": text}


def pub(v, minute):
    return {"type": "published", "version": v, "at": f"2026-11-12T09:{minute:02d}:30Z"}


def write(posts, records, md=POST):
    d = posts / "rivers"
    d.mkdir(parents=True, exist_ok=True)
    (d / "post.md").write_text(md)
    (d / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [{"ledger_trace": 1, "post": "rivers"}, *records]))


V1 = [x("x1", 1), snap("x1", "One."), pub(1, 2)]
V2 = V1 + [x("x2", 3), snap("x2", "One. Two."), pub(2, 4)]


def test_one_version(tmp_path):
    write(tmp_path / "posts", V1)
    build(tmp_path / "posts", tmp_path / "docs")
    page = (tmp_path / "docs" / "rivers" / "v1" / "index.html").read_text()
    assert page == render(POST, V1)
    assert (tmp_path / "docs" / "rivers" / "index.html").read_text() == page
    assert not (tmp_path / "docs" / "rivers" / "v2").exists()


def test_two_versions(tmp_path):
    write(tmp_path / "posts", V2)
    build(tmp_path / "posts", tmp_path / "docs")
    r = tmp_path / "docs" / "rivers"
    assert (r / "v1" / "index.html").read_text() == render(POST, V1)
    assert (r / "v2" / "index.html").read_text() == render(POST, V2)
    assert (r / "index.html").read_text() == render(POST, V2)
    assert "Published v2" not in (r / "v1" / "index.html").read_text()


def test_a_draft_after_the_last_publish_is_not_shown(tmp_path):
    write(tmp_path / "posts", V1 + [x("x2", 3), snap("x2", "One. Draft.")])
    build(tmp_path / "posts", tmp_path / "docs")
    page = (tmp_path / "docs" / "rivers" / "index.html").read_text()
    assert page == render(POST, V1)
    assert "Draft" not in page and "Px2" not in page


def test_a_rebuild_leaves_old_versions_alone(tmp_path):
    write(tmp_path / "posts", V2)
    build(tmp_path / "posts", tmp_path / "docs")
    r = tmp_path / "docs" / "rivers"
    old = {p: p.read_bytes() for p in (r / "v1").rglob("*") if p.is_file()}
    old.update({p: p.read_bytes() for p in (r / "v2").rglob("*") if p.is_file()})
    v3 = V2 + [x("x3", 5), snap("x3", "One. Two. Three."), pub(3, 6)]
    new_md = "---\ntitle: Rivers, renamed\n---\nText.\n"
    write(tmp_path / "posts", v3, new_md)
    build(tmp_path / "posts", tmp_path / "docs")
    assert {p: p.read_bytes() for p in old} == old
    assert (r / "v3" / "index.html").read_text() == render(new_md, v3)
    assert (r / "index.html").read_text() == render(new_md, v3)

"""Slice 8 (issue #20): build the site.

site.build(posts, out) builds the published site from a posts folder into out, and returns the
slugs it wrote, in index order. `ledger site <posts> [--out DIR]` does the same (out defaults to
"docs", both relative to the current folder) and exits 0.

- A post is a folder <posts>/<slug> holding trace.jsonl. Folders whose name starts with "." are
  never posts. A post is published if its trace has a record with type "published"; others are
  skipped, and nothing of theirs is written.
- For each published post: <out>/<slug>/index.html is site.render(post.md text, records),
  with post.md read as "" if it is missing; <out>/<slug>/post.md and <out>/<slug>/trace.jsonl
  are copies of the post's files, byte for byte (post.md only if it exists). Nothing else of the
  post's folder is copied (not its .ledger/, not anything else).
- <out>/index.html lists the published posts, newest first by their last published record's
  "at" (then by slug): a page like site.render's (same head lines, title "Posts", no script,
  nothing loaded from elsewhere) whose body has <h1>Posts</h1> and then <ul>, one line per post
  <li><a href="<slug>/">TITLE</a></li> (TITLE as site.render finds it, escaped), and </ul>.
- <out>/.nojekyll, empty.
- Nothing is written outside out. out and its folders are created if needed.
"""

import json
import subprocess
import sys
from pathlib import Path

from ledger.site import build, render

LEDGER = Path(sys.executable).parent / "ledger"


def x(id):
    return {"type": "exchange", "id": id, "at": "2026-11-11T09:00:00Z", "source": "claude-code",
            "model": "claude-opus-5-5", "prompt": "P", "reply": "R", "tools": []}


def published(v, at):
    return {"type": "published", "version": v, "at": at}


def post(posts, slug, title, records, extra=None):
    d = posts / slug
    d.mkdir(parents=True)
    if title is not None:
        (d / "post.md").write_text(f"---\ntitle: {title}\n---\n\nText.\n")
    lines = [{"ledger_trace": 1, "post": slug}, *records]
    (d / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
    for name, text in (extra or {}).items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


def files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_a_published_post_and_its_files(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "docs"
    d = post(posts, "a-post", "A post", [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    assert build(posts, out) == ["a-post"]
    assert files(out) == [".nojekyll", "a-post/index.html", "a-post/post.md", "a-post/trace.jsonl", "a-post/v1/index.html", "index.html"]
    assert (out / ".nojekyll").read_text() == ""
    assert (out / "a-post" / "post.md").read_bytes() == (d / "post.md").read_bytes()
    assert (out / "a-post" / "trace.jsonl").read_bytes() == (d / "trace.jsonl").read_bytes()
    records = [json.loads(l) for l in (d / "trace.jsonl").read_text().splitlines()]
    assert (out / "a-post" / "index.html").read_text() == render((d / "post.md").read_text(), records)


def test_unpublished_and_dot_folders_are_skipped(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "docs"
    post(posts, "draft", "Draft", [x("x1")])
    post(posts, ".ledger", "Hidden", [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    post(posts, "live", "Live", [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    (posts / "notes").mkdir()
    assert build(posts, out) == ["live"]
    assert not (out / "draft").exists() and not (out / ".ledger").exists() and not (out / "notes").exists()
    assert "Draft" not in (out / "index.html").read_text()


def test_nothing_of_dot_ledger_or_other_files_is_copied(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "docs"
    post(posts, "a-post", "A post", [x("x1"), published(1, "2026-11-11T10:00:00Z")],
         extra={".ledger/snapshots.jsonl": "secret", "notes.txt": "mine", "img/a.png": "png"})
    build(posts, out)
    assert files(out / "a-post") == ["index.html", "post.md", "trace.jsonl", "v1/index.html"]
    assert "secret" not in "".join((out / f).read_text() for f in files(out))


def test_missing_post_md(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "docs"
    post(posts, "a-post", None, [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    build(posts, out)
    assert files(out / "a-post") == ["index.html", "trace.jsonl", "v1/index.html"]
    assert "<title>Untitled</title>" in (out / "a-post" / "index.html").read_text()


def test_the_index_newest_first(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "docs"
    post(posts, "old", "Old one", [x("x1"), published(1, "2026-11-01T10:00:00Z")])
    post(posts, "revised", "Fish & chips", [x("x1"), published(1, "2026-10-01T10:00:00Z"),
                                            x("x2"), published(2, "2026-11-05T10:00:00Z")])
    post(posts, "b-new", "B", [x("x1"), published(1, "2026-11-03T10:00:00Z")])
    post(posts, "a-new", "A", [x("x1"), published(1, "2026-11-03T10:00:00Z")])
    assert build(posts, out) == ["revised", "a-new", "b-new", "old"]
    ls = (out / "index.html").read_text().split("\n")
    assert ls[:6] == ['<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
                      '<meta name="viewport" content="width=device-width, initial-scale=1">', '<title>Posts</title>']
    i = ls.index("<h1>Posts</h1>")
    assert ls[i + 1: i + 7] == ["<ul>",
                                '<li><a href="revised/">Fish &amp; chips</a></li>',
                                '<li><a href="a-new/">A</a></li>',
                                '<li><a href="b-new/">B</a></li>',
                                '<li><a href="old/">Old one</a></li>',
                                "</ul>"]
    page = "\n".join(ls)
    assert "<script" not in page and "src=" not in page and "://" not in page


def test_nothing_outside_out(tmp_path):
    posts, out = tmp_path / "posts", tmp_path / "site" / "docs"
    post(posts, "a-post", "A post", [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    before = set(files(tmp_path))
    build(posts, out)
    after = set(files(tmp_path))
    assert all(f.startswith("site/docs/") for f in after - before)
    assert before <= after


def test_the_command(tmp_path):
    post(tmp_path / "posts", "a-post", "A post", [x("x1"), published(1, "2026-11-11T10:00:00Z")])
    r = subprocess.run([str(LEDGER), "site", "posts"], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "docs" / "a-post" / "index.html").exists()
    r = subprocess.run([str(LEDGER), "site", "posts", "--out", "public"], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "public" / ".nojekyll").exists()

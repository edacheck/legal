"""Render one complete edition into an empty private staging directory."""

import html
import json

from common import ROOT, digest, document, execute, registration_links, version_url

ASSETS = {"index.html", "style.css", "CNAME", ".nojekyll", "registration-links.json"}


def page(config, title, body, prefix=""):
    navigation = " ".join(
        f'<a href="{prefix}{slug}/index.html">{html.escape(label)}</a>'
        for slug, label in config["documents"].items()
    )
    robots = "noindex, nofollow" if config["status"] == "draft" else "index, follow"
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="{robots}">
<title>{html.escape(title)} | Едачек</title>
<link rel="stylesheet" href="{prefix}style.css"></head><body>
<nav aria-label="Документы"><a href="{prefix}index.html">Едачек</a> {navigation}</nav>
<main>{body}</main>
<footer>ООО "ЕДАЧЕК". <a href="mailto:edacheckru@gmail.com">edacheckru@gmail.com</a></footer>
</body></html>
'''


def inputs():
    return {name: digest((ROOT / name).read_bytes()) for name in ("style.css", "pdf.typ")}


def render(config, versions, output):
    output.mkdir()
    manifest = {"edition": config, "tools": versions, "documents": {}, "assets": {},
                "inputs": inputs()}
    for slug, title in config["documents"].items():
        content = document(config, slug).encode("utf-8")
        tree = execute(["pandoc", "-f", "markdown-smart", "-t", "json"], content)
        article = execute(["pandoc", "-f", "json", "-t", "html5"], tree).decode("utf-8")
        for target in config["documents"]:
            article = article.replace(f'href="{version_url(config, target)}"',
                                      f'href="../{target}/index.html"')
        destination = output / slug
        destination.mkdir()
        pdf_name = f"{slug}-{config['version']}.pdf"
        download = f'<p><a href="{pdf_name}" download>Скачать эту редакцию в PDF</a></p>'
        markup = page(config, title, download + f"<article>{article}</article>", "../")
        (destination / "index.html").write_text(markup, encoding="utf-8")
        pdf_path = destination / pdf_name
        result = execute([
            "pandoc", "-f", "json", "--pdf-engine=typst", "--template", str(ROOT / "pdf.typ"),
            "--metadata", "title=" + title, "-o", str(pdf_path),
        ], tree)
        if result:
            raise ValueError("Unexpected PDF conversion output")
        manifest["documents"][slug] = {
            "url": version_url(config, slug),
            "source_sha256": digest((ROOT / "documents" / f"{slug}.md").read_bytes()),
            "document_sha256": digest(content), "ast_sha256": digest(tree),
            "html": f"{slug}/index.html", "html_sha256": digest(markup.encode("utf-8")),
            "pdf": f"{slug}/{pdf_name}", "pdf_sha256": digest(pdf_path.read_bytes()),
        }
    intro = '<h1>Юридические документы Едачек</h1>'
    if config["status"] == "draft":
        intro += '<p>Проекты для согласования. Не вступили в силу.</p>'
    intro += '<p>Выберите документ в меню. На каждой странице доступна та же редакция в PDF.</p>'
    assets = {"index.html": page(config, "Юридические документы", intro).encode("utf-8"),
              "style.css": (ROOT / "style.css").read_bytes(),
              "CNAME": (config["domain"] + "\n").encode("ascii"), ".nojekyll": b"",
              "registration-links.json": (json.dumps(registration_links(config),
                                                    indent=2) + "\n").encode("utf-8")}
    for name, content in assets.items():
        (output / name).write_bytes(content)
        manifest["assets"][name] = digest(content)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

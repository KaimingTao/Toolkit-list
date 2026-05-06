#!/usr/bin/env python3
import csv
import time
import html
from pathlib import Path


def to_url(s: str) -> str:
    s = (s or "").strip()
    # If there's no scheme, assume https
    if s and not (
        s.startswith(("http://", "https://", "ftp://", "file://", "mailto:"))
    ):
        s = "https://" + s
    return s


def bookmarks_html(rows, folder_name="Imported from CSV"):
    now = str(int(time.time()))
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
        f'<DT><H3 ADD_DATE="{now}" LAST_MODIFIED="{now}">{html.escape(folder_name)}</H3>',
        "<DL><p>",
    ]

    seen = set()
    for url_raw, title_raw in rows:
        url = to_url(url_raw)
        title = (title_raw or "").strip()
        if not url or not title:
            continue
        key = (url, title)
        if key in seen:
            continue
        seen.add(key)

        lines.append(
            f'<DT><A HREF="{html.escape(url, quote=True)}" ADD_DATE="{now}">'
            f"{html.escape(title)}</A>"
        )

    lines += ["</DL><p>", "</DL><p>"]
    return "\n".join(lines)


def convert_csv_to_bookmarks(
    csv_path: str, out_html_path: str, folder_name="Imported from CSV"
):
    csv_path = Path(csv_path)
    out_html_path = Path(out_html_path)

    rows = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Expecting columns: id (URL), text (title)
        for row in reader:
            rows.append(("" + row.get("\ufeffurl", ""), row.get("\ufeffurl", "")))

    print(len(rows))
    print(rows[:10])
    html_text = bookmarks_html(rows, folder_name=folder_name)
    out_html_path.write_text(html_text, encoding="utf-8")


if __name__ == "__main__":
    # Change these paths as needed:
    convert_csv_to_bookmarks(
        csv_path="2024-08-04.csv",
        out_html_path="bookmarks.html",
        folder_name="Imported from CSV",
    )

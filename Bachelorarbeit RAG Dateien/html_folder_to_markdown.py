import os
import sys
from bs4 import BeautifulSoup, NavigableString

def clean_html_to_markdown(html: str, source_name: str):
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in ["script", "style", "nav", "footer", "header", "aside"]:
        for t in soup.find_all(tag_name):
            t.decompose()

    for element in list(soup.descendants):
        if isinstance(element, NavigableString):
            if not element.strip():
                element.extract()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else source_name

    main = soup.find("main")
    if not main:
        main = soup.find("article")
    if not main:
        main = soup.find("body") or soup

    lines = []
    for element in main.descendants:
        if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(element.name[1])
            prefix = "#" * level
            text = element.get_text(" ", strip=True)
            if text:
                lines.append(f"{prefix} {text}")
        elif element.name in ["p", "li"]:
            text = element.get_text(" ", strip=True)
            if text:
                if element.name == "li":
                    lines.append(f"- {text}")
                else:
                    lines.append(text)

    text = "\n\n".join(lines).strip()

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        link_text = a.get_text(" ", strip=True) or href
        links.append((link_text, href))

    md_parts = []
    md_parts.append(f"# {title}\n")
    md_parts.append(f"_Quelle (lokale Datei): {source_name}_\n")

    if text:
        md_parts.append("\n---\n")
        md_parts.append(text)

    if links:
        md_parts.append("\n\n---\n")
        md_parts.append("## Weiterführende Links auf dieser Seite\n")
        for link_text, link_url in links:
            md_parts.append(f"- [{link_text}]({link_url})")

    content = "\n".join(md_parts).strip() + "\n"
    return content


def main():
    if len(sys.argv) < 3:
        print("Usage: python html_folder_to_markdown.py <html_input_dir> <markdown_output_dir>")
        sys.exit(1)

    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    for filename in os.listdir(in_dir):
        if not filename.lower().endswith(".html") and not filename.lower().endswith(".htm"):
            continue

        in_path = os.path.join(in_dir, filename)
        with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()

        md = clean_html_to_markdown(html, filename)
        base, _ = os.path.splitext(filename)
        out_path = os.path.join(out_dir, base + ".md")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"[OK] {in_path} -> {out_path}")


if __name__ == "__main__":
    main()

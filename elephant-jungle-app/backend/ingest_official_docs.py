from __future__ import annotations

import argparse
import io
import json
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


DEFAULT_API_BASE = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class SourceDoc:
    title: str
    url: str
    project: str
    doc_type: str
    language: str = "en"
    source: str = "Official Docs"
    source_type: str = "official"
    category: str = "foundation"
    region: str | None = None
    summary: str | None = None


DOCS: list[SourceDoc] = [
    SourceDoc(
        title="Bitcoin Whitepaper",
        url="https://bitcoin.org/bitcoin.pdf",
        project="Bitcoin",
        doc_type="whitepaper",
        summary="The original Bitcoin whitepaper.",
    ),
    SourceDoc(
        title="Bitcoin Developer Guide Introduction",
        url="https://developer.bitcoin.org/devguide/index.html",
        project="Bitcoin",
        doc_type="documentation",
        summary="Official Bitcoin developer guide overview.",
    ),
    SourceDoc(
        title="Ethereum Whitepaper",
        url="https://ethereum.org/en/whitepaper/",
        project="Ethereum",
        doc_type="whitepaper",
        summary="Ethereum whitepaper landing page and canonical references.",
    ),
    SourceDoc(
        title="Intro to Ethereum",
        url="https://ethereum.org/en/developers/docs/intro-to-ethereum/",
        project="Ethereum",
        doc_type="documentation",
        summary="Official introduction to Ethereum concepts.",
    ),
    SourceDoc(
        title="Solana Documentation Introduction",
        url="https://solana.com/docs/intro/quick-start",
        project="Solana",
        doc_type="documentation",
        summary="Official Solana introduction and quick start.",
    ),
    SourceDoc(
        title="Uniswap Protocol Concepts",
        url="https://docs.uniswap.org/concepts/uniswap-protocol",
        project="Uniswap",
        doc_type="documentation",
        category="defi",
        summary="Official overview of the Uniswap protocol.",
    ),
    SourceDoc(
        title="Aave V3 Overview",
        url="https://aave.com/docs/developers/aave-v3/overview",
        project="Aave",
        doc_type="documentation",
        category="defi",
        summary="Official overview of Aave V3.",
    ),
    SourceDoc(
        title="Chainlink Price Feeds",
        url="https://docs.chain.link/data-feeds/price-feeds",
        project="Chainlink",
        doc_type="documentation",
        category="oracle",
        summary="Official Chainlink price feeds overview.",
    ),
]


def clean_line(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def join_structured_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    previous_blank = False
    for raw in lines:
        line = clean_line(raw)
        if not line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue
        previous_blank = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    lines: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_lines = [clean_line(line) for line in text.splitlines()]
        page_lines = [line for line in page_lines if line]
        if not page_lines:
            continue
        lines.append(f"## Page {index}")
        lines.extend(page_lines)
        lines.append("")
    return join_structured_lines(lines)


def extract_html_text(content: bytes, url: str) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for tag_name in ["script", "style", "noscript", "svg"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines: list[str] = []
    title = soup.title.get_text(" ", strip=True) if soup.title else url
    lines.append(f"# {title}")
    lines.append("")

    for element in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "table"]):
        if element.name in {"h1", "h2", "h3", "h4"}:
            text = element.get_text(" ", strip=True)
            if text:
                lines.append(f"## {text}")
                lines.append("")
            continue

        if element.name == "li":
            text = element.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
            continue

        if element.name == "table":
            for row in element.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                cells = [cell for cell in cells if cell]
                if cells:
                    lines.append(" | ".join(cells))
            lines.append("")
            continue

        text = element.get_text(" ", strip=True)
        if text:
            lines.append(text)
            lines.append("")

    return join_structured_lines(lines)


def fetch_text(doc: SourceDoc, timeout: int = 60) -> str:
    response = requests.get(
        doc.url,
        timeout=timeout,
        headers={"User-Agent": "ElephantJungleKnowledgeSeeder/1.0"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()

    if doc.url.lower().endswith(".pdf") or "application/pdf" in content_type:
        return extract_pdf_text(response.content)
    return extract_html_text(response.content, doc.url)


def ingest_doc(api_base: str, doc: SourceDoc, content: str) -> dict:
    payload = {
        "source": doc.source,
        "title": doc.title,
        "url": doc.url,
        "published_at": None,
        "doc_type": doc.doc_type,
        "project": doc.project,
        "category": doc.category,
        "region": doc.region,
        "source_type": doc.source_type,
        "language": doc.language,
        "summary": doc.summary,
        "content": content,
    }
    response = requests.post(
        f"{api_base.rstrip('/')}/ingest",
        json=payload,
        timeout=120,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch official blockchain docs and ingest them.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    args = parser.parse_args()

    results: list[dict] = []
    for doc in DOCS:
        content = fetch_text(doc)
        if len(content) < 400:
            raise RuntimeError(f"Fetched content too short for {doc.title}: {len(content)} chars")
        result = ingest_doc(args.api_base, doc, content)
        results.append(
            {
                "title": doc.title,
                "project": doc.project,
                "url": doc.url,
                "chars": len(content),
                "chunks": result.get("chunks", 0),
                "document_id": result.get("document_id"),
            }
        )
        print(json.dumps(results[-1], ensure_ascii=False))

    print(json.dumps({"ingested": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

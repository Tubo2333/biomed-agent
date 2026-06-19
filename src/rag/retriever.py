# retriever.py — PubMed EUtils 检索 + XML 解析 + 本地缓存
#
# 整合自 CSTB_paper/references/fetch_pubmed.py 的 API 调用模式。
# 使用 fetch_with_retry (3-retry + exponential backoff) 替代裸 urllib。

from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from src.types import Paper, SearchQuery, SearchResult
from src.utils.network import fetch_with_retry

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "BioMed-Agent/1.0 (BioMedical Research Assistant)"
DEFAULT_CACHE_DIR = "data/pubmed_cache"


# ═══════════════════════════════════════════════════════════════
# PubMedRetriever
# ═══════════════════════════════════════════════════════════════


class PubMedAPIError(Exception):
    """PubMed API 返回错误（重试耗尽后）。"""
    pass


class PubMedRetriever:
    """PubMed EUtils 检索 + 结果解析 + 本地缓存。

    Usage:
        retriever = PubMedRetriever(cache_dir="./data/pubmed_cache")
        result = retriever.search(
            SearchQuery("CSTB[gene] AND colorectal cancer[MeSH]", max_results=50)
        )
    """

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("PubMedRetriever initialized, cache=%s", self._cache_dir)

    # ── Public API ──────────────────────────────────────────

    def search(self, query: SearchQuery, retrieval_round: int = 1) -> SearchResult:
        """执行 PubMed 检索。

        步骤：
        1. 检查本地缓存（query string hash → 缓存文件）
        2. 缓存未命中 → esearch → efetch → 解析 XML
        3. 写入缓存
        4. 返回 SearchResult

        Args:
            query: 检索查询（含 query_string, max_results, sort_by, date_range）
            retrieval_round: 第几轮检索

        Returns:
            SearchResult，含 Paper 列表

        Raises:
            NetworkError: 代理不可用
            PubMedAPIError: EUtils 返回错误（3 次重试后）
        """
        # ── 1. 检查缓存 ──
        cache_key = self._cache_key(query.query_string)
        cached = self._load_cache(cache_key)
        if cached is not None:
            logger.info(
                "Cache HIT for query: '%s...' (%d papers)",
                query.query_string[:80],
                len(cached),
            )
            return SearchResult(
                query=query,
                papers=cached,
                total_count=len(cached),
                retrieval_round=retrieval_round,
            )

        # ── 2. esearch — 获取 PMID 列表 ──
        pmid_list, total_count = self._search_pmids(query)
        if not pmid_list:
            logger.warning("PubMed esearch returned 0 results for: '%s'", query.query_string)
            return SearchResult(
                query=query,
                papers=[],
                total_count=0,
                retrieval_round=retrieval_round,
            )

        # ── 3. efetch — 获取完整记录 ──
        raw_xml = self._fetch_details(pmid_list)
        papers = self._parse_efetch_xml(raw_xml)

        # ── 4. 写入缓存 ──
        self._save_cache(cache_key, papers)

        logger.info(
            "PubMed search complete: '%s...' → %d papers (total: %d)",
            query.query_string[:80],
            len(papers),
            total_count,
        )

        return SearchResult(
            query=query,
            papers=papers,
            total_count=total_count,
            retrieval_round=retrieval_round,
        )

    # ── esearch ─────────────────────────────────────────────

    def _search_pmids(self, query: SearchQuery) -> tuple[list[str], int]:
        """PubMed esearch → PMID 列表 + 总数。

        Returns:
            (pmid_list, total_count)
        """
        params = [
            ("db", "pubmed"),
            ("term", query.query_string),
            ("retmax", str(query.max_results)),
            ("retmode", "json"),
            ("sort", query.sort_by),
        ]
        if query.date_range:
            params.append(
                ("mindate", str(query.date_range[0])),
            )
            params.append(
                ("maxdate", str(query.date_range[1])),
            )
            params.append(("datetype", "pdat"))

        query_string = urllib.parse.urlencode(params)
        url = f"{PUBMED_ESEARCH}?{query_string}"

        try:
            raw = fetch_with_retry(
                url,
                max_retries=3,
                base_timeout=30,
                headers={"User-Agent": USER_AGENT},
            )
            data = json.loads(raw)
            result = data.get("esearchresult", {})
            idlist = result.get("idlist", [])
            total = int(result.get("count", "0"))
            return idlist, total
        except json.JSONDecodeError as e:
            raise PubMedAPIError(
                f"Failed to parse PubMed esearch response: {e}"
            ) from e

    # ── efetch ─────────────────────────────────────────────

    def _fetch_details(self, pmid_list: list[str]) -> str:
        """PubMed efetch → XML 字符串。

        efetch 返回 XML 格式的完整论文记录（含摘要）。
        """
        pmid_str = ",".join(pmid_list)
        url = (
            f"{PUBMED_EFETCH}?db=pubmed&id={pmid_str}"
            f"&retmode=xml&rettype=abstract"
        )
        return fetch_with_retry(
            url,
            max_retries=3,
            base_timeout=30,
            headers={"User-Agent": USER_AGENT},
        )

    # ── XML 解析 ────────────────────────────────────────────

    @staticmethod
    def _parse_efetch_xml(xml_str: str) -> list[Paper]:
        """解析 PubMed efetch XML → Paper 列表。

        从每个 <PubmedArticle> 元素中提取：
        - PMID, Title, Abstract, Authors, Journal, Year, DOI
        """
        papers: list[Paper] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise PubMedAPIError(f"Failed to parse PubMed efetch XML: {e}") from e

        for article_elem in root.findall(".//PubmedArticle"):
            try:
                paper = PubMedRetriever._parse_article(article_elem)
                if paper:
                    papers.append(paper)
            except Exception as e:
                logger.warning("Failed to parse a PubmedArticle: %s", e)
                continue

        return papers

    @staticmethod
    def _parse_article(elem: ET.Element) -> Optional[Paper]:
        """解析单个 <PubmedArticle> 元素。"""
        # PMID
        pmid_elem = elem.find(".//PMID")
        pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else ""
        if not pmid:
            return None

        # Article node
        article = elem.find(".//Article")
        if article is None:
            return None

        # Title
        title_elem = article.find("./ArticleTitle")
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

        # Abstract — collect all AbstractText elements
        abstract_parts: list[str] = []
        if article.find("./Abstract") is not None:
            for abs_elem in article.findall("./Abstract/AbstractText"):
                label = abs_elem.get("Label", "")
                text = abs_elem.text or ""
                if label:
                    abstract_parts.append(f"{label}: {text.strip()}")
                else:
                    abstract_parts.append(text.strip())
        abstract = " ".join(abstract_parts)

        # Authors
        authors: list[str] = []
        author_list = article.find("./AuthorList")
        if author_list is not None:
            for auth_elem in author_list.findall("./Author"):
                last = auth_elem.findtext("./LastName") or ""
                fore = auth_elem.findtext("./ForeName") or ""
                if last:
                    full = f"{last} {fore}".strip()
                    authors.append(full)

        # Journal
        journal_elem = article.find("./Journal")
        journal = ""
        if journal_elem is not None:
            iso = journal_elem.findtext("./ISOAbbreviation")
            if iso:
                journal = iso
            else:
                title_j = journal_elem.findtext("./Title")
                if title_j:
                    journal = title_j

        # Year
        year = 0
        if journal_elem is not None:
            pubdate = journal_elem.find("./JournalIssue/PubDate")
            if pubdate is not None:
                year_str = (
                    pubdate.findtext("./Year")
                    or pubdate.findtext("./MedlineDate", "")
                )
                if year_str:
                    # MedlineDate can be "2020 Jan-Feb", take first 4 digits
                    year_str = year_str.strip()[:4]
                    try:
                        year = int(year_str)
                    except ValueError:
                        pass

        # DOI
        doi: Optional[str] = None
        for eid in elem.findall(".//ELocationID"):
            if eid.get("EIdType") == "doi" and eid.text:
                doi = eid.text.strip()
                break
        if doi is None:
            for aid in article.findall(".//ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text.strip()
                    break

        return Paper(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            year=year,
            doi=doi,
        )

    # ── 缓存 ────────────────────────────────────────────────

    @staticmethod
    def _cache_key(query_string: str) -> str:
        """为查询字符串生成缓存 key（SHA256 前 12 位）。"""
        return hashlib.sha256(query_string.encode("utf-8")).hexdigest()[:12]

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _load_cache(self, cache_key: str) -> Optional[list[Paper]]:
        """加载缓存。返回 None 表示未命中。"""
        path = self._cache_path(cache_key)
        if not path.exists():
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            papers = []
            for d in data:
                papers.append(
                    Paper(
                        pmid=d.get("pmid", ""),
                        title=d.get("title", ""),
                        abstract=d.get("abstract", ""),
                        authors=d.get("authors", []),
                        journal=d.get("journal", ""),
                        year=d.get("year", 0),
                        doi=d.get("doi"),
                    )
                )
            return papers
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Cache corrupted for key=%s: %s. Invalidating.", cache_key, e)
            path.unlink(missing_ok=True)
            return None

    def _save_cache(self, cache_key: str, papers: list[Paper]) -> None:
        """写入缓存。"""
        data = [
            {
                "pmid": p.pmid,
                "title": p.title,
                "abstract": p.abstract,
                "authors": p.authors,
                "journal": p.journal,
                "year": p.year,
                "doi": p.doi,
            }
            for p in papers
        ]
        path = self._cache_path(cache_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

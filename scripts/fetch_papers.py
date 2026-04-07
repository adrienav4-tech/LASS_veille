"""
LASS Veille — Script de collecte multi-sources
Auteur : adrienav4-tech
Sources : arXiv, Semantic Scholar, IEEE Xplore, Google Scholar (scholarly)
Exécuté chaque jour à 6h00 UTC par GitHub Actions
"""

import json
import os
import re
import time
import hashlib
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import arxiv
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ==============================================================
# BASE DE MOTS-CLÉS
# ==============================================================
KEYWORDS = {
    "core": [
        # Termes longs (matching exact dans les résumés)
        "Language-Augmented Audio Source Separation",
        "LASS",
        "text-queried audio",
        "text-based sound separation",
        "natural language audio separation",
        "query-based source separation",
        "language-conditioned audio",
    ],
    "models": [
        "AudioSep",
        "CLAP",
        "AudioLDM",
        "MixIT",
        "SoundBeam",
        "EzAudio",
        "WavJourney",
        "UniAudio",
        "Whispering",
    ],
    "methods": [
        "contrastive language audio",
        "universal sound separation",
        "conditional source separation",
        "audio source separation",
        "sound source separation",
        "music source separation",
        "speech separation",
        "audio spectrogram transformer",
        "mask-based separation",
        "text-driven separation",
    ],
    "applications": [
        "environmental sound",
        "audio foundation model",
        "multimodal audio",
        "speech enhancement",
        "music demixing",
        "foley sound",
    ],
}

# Liste plate pour le scoring — on utilise les termes courts
SCORE_KEYWORDS = [
    # Score élevé : termes très spécifiques LASS
    "audio source separation", "sound separation", "source separation",
    "language-augmented", "text-queried", "text-based sound",
    "audiosep", "clap", "audioldm", "mixup", "soundbeam",
    "contrastive language audio", "universal sound separation",
    # Score moyen : domaine audio général
    "speech separation", "music separation", "music demixing",
    "audio foundation", "sound event", "audio generation",
    "spectrogram", "mel-spectrogram", "stft", "waveform",
]

# Toutes les requêtes aplaties (pour compatibilité)
ALL_QUERIES = [q for group in KEYWORDS.values() for q in group]

# ==============================================================
# CONFIG
# ==============================================================
MAX_RESULTS_PER_SOURCE = 25
MAX_FINAL = 25
DAYS_LOOKBACK = 90  # Fenêtre de recherche en jours
DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "lass_papers.json")

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_KEY = os.environ.get("SEMANTIC_SCHOLAR_KEY", "")

IEEE_API = "https://ieeexplore.ieee.org/rest/search"
IEEE_KEY = os.environ.get("IEEE_API_KEY", "")

# ==============================================================
# UTILITAIRES
# ==============================================================

def paper_id(title: str) -> str:
    """Hash court pour déduplications."""
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]


def normalize_date(date_str: str) -> str:
    """Normalise une date en YYYY-MM-DD."""
    if not date_str:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y/%m/%d", "%d %B %Y"):
        try:
            return datetime.strptime(date_str[:10], fmt[:len(date_str[:10])]).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str[:10]


def relevance_score(paper: dict, keywords: list = None) -> int:
    """Score de pertinence basé sur SCORE_KEYWORDS (termes courts).
    Un article arXiv de cs.SD sur la séparation de sources doit scorer >= 1.
    """
    score = 0
    title = (paper.get("title") or "").lower()
    summary = (paper.get("summary") or "").lower()
    # Utilise toujours SCORE_KEYWORDS — plus court = meilleur matching
    for kw in SCORE_KEYWORDS:
        kw_low = kw.lower()
        if kw_low in title:
            score += 3   # dans le titre = très pertinent
        elif kw_low in summary:
            score += 1   # dans le résumé = pertinent
    return score


def deduplicate(papers: list) -> list:
    """Supprime les doublons par hash de titre."""
    seen = set()
    unique = []
    for p in papers:
        pid = paper_id(p.get("title", ""))
        if pid not in seen:
            seen.add(pid)
            unique.append(p)
    return unique


def tag_paper(paper: dict) -> list:
    """Attribue des tags thématiques à un article."""
    tags = []
    text = ((paper.get("title") or "") + " " + (paper.get("summary") or "")).lower()
    tag_rules = {
        "LASS": ["language-augmented", "lass"],
        "AudioSep": ["audiosep"],
        "CLAP": ["clap", "contrastive language audio"],
        "AudioLDM": ["audioldm"],
        "Music": ["music", "musical"],
        "Speech": ["speech", "voice"],
        "Diffusion": ["diffusion", "ldm"],
        "Transformer": ["transformer", "attention"],
        "U-Net": ["u-net", "unet"],
        "IEEE": ["icassp", "interspeech", "waspaa"],
    }
    for tag, patterns in tag_rules.items():
        if any(p in text for p in patterns):
            tags.append(tag)
    return tags[:4]


# ==============================================================
# SOURCE 1 : arXiv
# ==============================================================

# Requêtes arXiv optimisées : termes courts + catégories audio
# On utilise la syntaxe arXiv : ti/abs + catégories cs.SD et eess.AS
ARXIV_QUERIES = [
    # Termes cœur LASS — larges, matchent beaucoup
    'ti:"audio source separation"',
    'ti:"sound separation"',
    'abs:"language-augmented" AND abs:"audio"',
    'abs:"text-queried" AND abs:"audio"',
    'abs:"text-based" AND abs:"sound separation"',
    # Modèles connus
    'ti:"AudioSep"',
    'abs:"AudioSep"',
    'ti:"CLAP" AND abs:"audio"',
    'abs:"contrastive language-audio"',
    # Méthodes générales audio — catégories ciblées
    'cat:cs.SD AND abs:"source separation"',
    'cat:eess.AS AND abs:"source separation"',
    'cat:cs.SD AND abs:"sound separation"',
    'cat:cs.SD AND abs:"speech separation"',
    'cat:cs.SD AND abs:"music separation"',
    # Foundation models audio
    'abs:"audio foundation model"',
    'abs:"universal sound separation"',
]

def fetch_arxiv(queries: list = None) -> list:
    """queries est ignoré — on utilise ARXIV_QUERIES optimisées."""
    log.info(f"arXiv — {len(ARXIV_QUERIES)} requêtes optimisées")
    papers = []
    client = arxiv.Client(page_size=25, delay_seconds=2.0)

    for query in ARXIV_QUERIES:
        try:
            search = arxiv.Search(
                query=query,
                max_results=25,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            for r in client.results(search):
                papers.append({
                    "title": r.title,
                    "authors": [a.name for a in r.authors],
                    "date": r.published.strftime("%Y-%m-%d") if r.published else "",
                    "summary": r.summary[:600],
                    "url": r.entry_id,
                    "source": "arxiv",
                    "tags": [],
                })
            time.sleep(2.0)
        except Exception as e:
            log.warning(f"arXiv error [{query}]: {e}")
    log.info(f"arXiv — {len(papers)} résultats bruts")
    return papers


# ==============================================================
# SOURCE 2 : Semantic Scholar
# ==============================================================

def fetch_semantic_scholar(queries: list) -> list:
    log.info(f"Semantic Scholar — {len(queries)} requêtes")
    papers = []
    headers = {}
    if SEMANTIC_SCHOLAR_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_KEY

    for query in queries[:6]:
        try:
            params = {
                "query": query,
                "fields": "title,authors,year,abstract,externalIds,publicationDate,venue",
                "limit": 8,
            }
            r = requests.get(SEMANTIC_SCHOLAR_API, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("data", []):
                url = ""
                ext = item.get("externalIds") or {}
                if ext.get("ArXiv"):
                    url = f"https://arxiv.org/abs/{ext['ArXiv']}"
                elif ext.get("DOI"):
                    url = f"https://doi.org/{ext['DOI']}"
                elif ext.get("CorpusId"):
                    url = f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}"

                papers.append({
                    "title": item.get("title", ""),
                    "authors": [a.get("name", "") for a in (item.get("authors") or [])],
                    "date": item.get("publicationDate") or str(item.get("year", "")),
                    "summary": (item.get("abstract") or "")[:500],
                    "url": url,
                    "source": "semantic",
                    "venue": item.get("venue", ""),
                    "tags": [],
                })
            time.sleep(1.5)
        except Exception as e:
            log.warning(f"Semantic Scholar error [{query}]: {e}")
    log.info(f"Semantic Scholar — {len(papers)} résultats bruts")
    return papers


# ==============================================================
# SOURCE 3 : IEEE Xplore
# ==============================================================

def fetch_ieee(queries: list) -> list:
    if not IEEE_KEY:
        log.warning("IEEE — clé API manquante (IEEE_API_KEY), source ignorée")
        return []
    log.info(f"IEEE Xplore — {len(queries)} requêtes")
    papers = []

    for query in queries[:5]:
        try:
            params = {
                "querytext": query,
                "apikey": IEEE_KEY,
                "max_records": 8,
                "sort_field": "publication_year",
                "sort_order": "desc",
                "start_year": datetime.now().year - 2,
            }
            r = requests.get(IEEE_API, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("articles", []):
                papers.append({
                    "title": item.get("title", ""),
                    "authors": [a.get("full_name", "") for a in (item.get("authors", {}).get("authors") or [])],
                    "date": str(item.get("publication_year", "")),
                    "summary": (item.get("abstract") or "")[:500],
                    "url": item.get("pdf_url") or item.get("html_url") or f"https://ieeexplore.ieee.org/document/{item.get('article_number', '')}",
                    "source": "ieee",
                    "venue": item.get("publication_title", ""),
                    "tags": [],
                })
            time.sleep(1.5)
        except Exception as e:
            log.warning(f"IEEE error [{query}]: {e}")
    log.info(f"IEEE — {len(papers)} résultats bruts")
    return papers


# ==============================================================
# SOURCE 4 : Google Scholar (scholarly)
# ==============================================================

def fetch_google_scholar(queries: list) -> list:
    try:
        from scholarly import scholarly, ProxyGenerator
    except ImportError:
        log.warning("Google Scholar — 'scholarly' non installé, source ignorée")
        return []

    log.info(f"Google Scholar — {len(queries)} requêtes")
    papers = []

    # Proxy optionnel pour éviter les bans
    pg = ProxyGenerator()
    use_proxy = pg.FreeProxies()
    if use_proxy:
        scholarly.use_proxy(pg)

    for query in queries[:5]:
        try:
            search_query = scholarly.search_pubs(query)
            count = 0
            for result in search_query:
                if count >= 5:
                    break
                bib = result.get("bib", {})
                url = result.get("eprint_url") or result.get("pub_url") or ""
                papers.append({
                    "title": bib.get("title", ""),
                    "authors": bib.get("author", []) if isinstance(bib.get("author"), list) else [bib.get("author", "")],
                    "date": str(bib.get("pub_year", "")),
                    "summary": (bib.get("abstract") or "")[:500],
                    "url": url,
                    "source": "scholar",
                    "venue": bib.get("venue", ""),
                    "tags": [],
                })
                count += 1
            time.sleep(3.0)  # Scholar est plus strict sur le rate-limit
        except Exception as e:
            log.warning(f"Google Scholar error [{query}]: {e}")
    log.info(f"Google Scholar — {len(papers)} résultats bruts")
    return papers


# ==============================================================
# PIPELINE PRINCIPAL
# ==============================================================

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # ==============================================================
    # CHARGEMENT DE L'ARCHIVE EXISTANTE
    # Les anciens articles sont toujours conservés et fusionnés avec
    # les nouveaux. On ne supprime jamais un article déjà indexé.
    # ==============================================================
    existing_papers = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_papers = json.load(f)
            log.info(f"Archive existante chargée : {len(existing_papers)} articles")
        except Exception as e:
            log.warning(f"Impossible de lire l'archive existante : {e}")

    # Sous-ensemble de requêtes pour chaque source
    core_queries = KEYWORDS["core"]
    model_queries = KEYWORDS["models"]
    method_queries = KEYWORDS["methods"]

    all_papers = []

    log.info("=== Démarrage de la collecte LASS ===")

    # Collecte parallèle (prudente — certains endpoints sont fragiles)
    with ThreadPoolExecutor(max_workers=2) as exe:
        futures = {
            exe.submit(fetch_arxiv, core_queries + model_queries): "arXiv",
            exe.submit(fetch_semantic_scholar, core_queries + method_queries): "SemanticScholar",
        }
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                results = future.result()
                all_papers.extend(results)
                log.info(f"{source_name} → {len(results)} articles récupérés")
            except Exception as e:
                log.error(f"{source_name} a échoué : {e}")

    # Sources séquentielles (plus fragiles, rate-limits stricts)
    all_papers.extend(fetch_ieee(core_queries + model_queries))
    all_papers.extend(fetch_google_scholar(core_queries[:3]))

    log.info(f"Total brut nouvelles collectes : {len(all_papers)} articles")

    # ==============================================================
    # FUSION : nouveaux articles + archive existante
    # Les nouveaux passent en premier (priorité au scoring),
    # les anciens complètent derrière. La déduplication élimine
    # ensuite les doublons — les nouveaux l'emportent sur les anciens
    # en cas de même titre (ils ont potentiellement un résumé + complet).
    # ==============================================================
    merged = all_papers + existing_papers
    log.info(f"Total après fusion avec archive : {len(merged)} articles")

    # Filtrage : supprimer les articles sans titre
    merged = [p for p in merged if p.get("title", "").strip()]

    # Déduplification (les nouveaux en tête sont conservés en priorité)
    merged = deduplicate(merged)
    log.info(f"Après déduplication : {len(merged)} articles")

    # Scoring de pertinence (utilise les termes courts de SCORE_KEYWORDS)
    for p in merged:
        p["_score"] = relevance_score(p)
        if not p.get("tags"):
            p["tags"] = tag_paper(p)

    # Seuil bas = 1 pour les nouveaux articles venant de requêtes ciblées
    # Les anciens articles archivés sont toujours conservés sans condition
    new_ids = {paper_id(p.get("title", "")) for p in all_papers}
    before = len(merged)
    merged = [
        p for p in merged
        if p["_score"] >= 1                                    # nouveau pertinent
        or paper_id(p.get("title", "")) not in new_ids         # ancien archivé
    ]
    log.info(f"Après filtrage pertinence : {len(merged)} articles (éliminés : {before - len(merged)})")

    # Tri : par date décroissante (les plus récents d'abord),
    # puis par score pour les ex-aequo
    merged.sort(key=lambda p: (p.get("date", ""), p["_score"]), reverse=True)

    # Pas de limite MAX_FINAL sur l'archive — on garde TOUT
    # Seule la page d'accueil affiche les 25 derniers via JS
    final_papers = merged

    # Nettoyage des champs internes
    for p in final_papers:
        p.pop("_score", None)

    # Écriture JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_papers, f, ensure_ascii=False, indent=2)

    log.info(f"=== Terminé : {len(final_papers)} articles écrits dans {OUTPUT_FILE} ===")

    # Affichage résumé par source
    from collections import Counter
    sources = Counter(p.get("source", "unknown") for p in final_papers)
    for src, count in sources.items():
        log.info(f"  {src}: {count} articles")


if __name__ == "__main__":
    main()
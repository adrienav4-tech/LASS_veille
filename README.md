# LASS Veille

Veille Technologique automatisée sur le **Language-Augmented Audio Source Separation**.

## Structure

```
├── index.html               # Interface web (page d'accueil + veille + concept + processus)
├── requirements.txt         # Dépendances Python
├── scripts/
│   └── fetch_papers.py      # Script de collecte multi-sources
├── data/
│   └── lass_papers.json     # Généré automatiquement par le script
└── .github/workflows/
    └── fetch_papers.yml     # GitHub Actions (cron 6h00 UTC)
```

## Sources agrégées

| Source | API | Clé requise |
|---|---|---|
| arXiv | `export.arxiv.org` | Non |
| Semantic Scholar | `api.semanticscholar.org` | Optionnelle (free) |
| IEEE Xplore | `ieeexplore.ieee.org/rest/search` | Oui (free tier) |
| Google Scholar | `scholarly` (scraping) | Non (fragile) |

## Secrets GitHub à configurer

Dans `Settings > Secrets > Actions` :
- `SEMANTIC_SCHOLAR_KEY` — clé API Semantic Scholar (https://www.semanticscholar.org/product/api)
- `IEEE_API_KEY` — clé API IEEE Xplore (https://developer.ieee.org/)

## Déploiement

GitHub Pages doit être activé sur la branche `gh-pages`.

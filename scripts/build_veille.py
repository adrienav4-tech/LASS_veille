import arxiv
import json
import re
import os
from datetime import datetime

# Configuration de la recherche LASS (Language-Augmented Audio Source Separation)
QUERY = 'abs:"Language-Augmented Audio" OR abs:"Audio Source Separation" OR all:"AudioSep" OR all:"Text-queried Audio"'
MAX_RESULTS = 25
JSON_PATH = "data/lass_papers.json"
README_PATH = "README.md"

def fetch_arxiv_papers():
    """Récupère les données depuis arXiv."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=QUERY,
        max_results=MAX_RESULTS,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    
    papers = []
    for paper in client.results(search):
        papers.append({
            "date": paper.published.strftime("%Y-%m-%d"),
            "title": paper.title.replace('\n', ' '),
            "authors": [a.name for a in paper.authors],
            "summary": paper.summary.replace('\n', ' ')[:300] + "...",
            "url": paper.entry_id
        })
    return papers

def export_to_json(papers):
    """Sauvegarde les données pour le site web."""
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)

def update_readme_table(papers):
    """Injecte un tableau Markdown dans le README sans écraser le reste."""
    with open(README_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Construction du nouveau tableau
    table = "| 📅 Date | 📄 Titre du Papier | 👥 Auteurs Principaux | 🔗 Lien |\n"
    table += "|---|---|---|---|\n"
    for p in papers:
        # Formate les auteurs (Max 2 + et al.)
        authors_str = ", ".join(p['authors'][:2])
        if len(p['authors']) > 2:
            authors_str += " *et al.*"
            
        table += f"| {p['date']} | **{p['title']}** | {authors_str} | [Lire]({p['url']}) |\n"

    # Remplacement via balises invisibles
    new_content = re.sub(
        r"(\n).*?(\n)",
        r"\1" + table + r"\2",
        content,
        flags=re.DOTALL
    )

    with open(README_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == "__main__":
    print("Démarrage de la veille LASS...")
    data = fetch_arxiv_papers()
    export_to_json(data)
    update_readme_table(data)
    print(f"Succès ! {len(data)} articles traités.")
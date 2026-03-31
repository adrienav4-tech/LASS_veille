// Fonction pour gérer le changement d'onglets
function openTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.style.display = 'none');
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(tabId).style.display = 'block';
    event.currentTarget.classList.add('active');
}

// Chargement asynchrone des 500+ sources depuis le JSON
document.addEventListener("DOMContentLoaded", () => {
    fetch('data/sources.json')
       .then(response => response.json())
       .then(data => {
            renderList(data.lass, 'lass-list');
            renderList(data.avss, 'avss-list');
            renderList(data.unimodal, 'unimodal-list');
        })
       .catch(error => console.error('Erreur de chargement des sources:', error));
});

function renderList(items, containerId) {
    const container = document.getElementById(containerId);
    if (!items || items.length === 0) {
        container.innerHTML = "<p>Aucune source disponible pour le moment.</p>";
        return;
    }

    items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'source-item';
        li.innerHTML = `
            <h3><a href="${item.url}" target="_blank">${item.title}</a></h3>
            <div>
                <span class="badge">${item.year}</span>
                <span class="badge">${item.authors}</span>
            </div>
            <p>${item.description}</p>
        `;
        container.appendChild(li);
    });
}
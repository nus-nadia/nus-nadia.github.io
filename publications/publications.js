let allPublications = [];
let filteredPublications = [];
let currentPage = 1;
const itemsPerPage = 5;

// Load publications
async function loadPublications() {
    try {
        const response = await fetch("publications.json");
        allPublications = await response.json();
        filteredPublications = [...allPublications];
        renderPublications();
        populateFilterOptions();
        setupFilters();
    } catch (error) {
        console.error("Error loading publications:", error);
    }
}

// Render visible publications
function renderPublications() {
    const container = document.getElementById("publication-list");
    container.innerHTML = "";

    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageItems = filteredPublications.slice(start, end);

    if (pageItems.length === 0) {
        container.innerHTML = `<p class="text-gray-500 text-center">No publications found.</p>`;
    } else {
        pageItems.forEach(pub => {
            const pubCard = document.createElement("div");
            pubCard.className = "publication-card bg-gray-50 p-6 rounded-lg shadow-md";
            pubCard.dataset.year = pub.year;
            pubCard.dataset.topics = pub.tags.join(",").toLowerCase();
            pubCard.dataset.title = pub.title.toLowerCase();
            pubCard.dataset.authors = pub.authors.toLowerCase();

            pubCard.innerHTML = `
                <div class="flex flex-col md:flex-row md:items-center md:justify-between">
                    <div class="mb-4 md:mb-0">
                        <h3 class="text-xl font-bold mb-2">${pub.title}</h3>
                        <p class="text-gray-600 mb-2">${pub.authors} (${pub.year}). 
                            <span class="italic">${pub.publication_info}</span>
                        </p>
                        <div class="flex flex-wrap gap-2 mt-2">
                            ${pub.tags.map(tag => `<span class="bg-blue-100 text-blue-800 text-xs px-3 py-1 rounded-full">${tag}</span>`).join("")}
                        </div>
                    </div>
                    <div class="flex space-x-4">
                        <a href="${pub.pdf_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="file-text"></i> PDF</a>
                        <a href="${pub.doi_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="external-link"></i> DOI</a>
                    </div>
                </div>
            `;
            container.appendChild(pubCard);
        });
    }

    updatePaginationControls();
    if (typeof feather !== "undefined") feather.replace();
}

// Update pagination
function updatePaginationControls() {
    const paginationContainer = document.querySelector(".pagination-container");
    const totalPages = Math.ceil(filteredPublications.length / itemsPerPage);
    const pageNumbersContainer = document.getElementById("pageNumbers");
    const prevBtn = document.getElementById("prevPage");
    const nextBtn = document.getElementById("nextPage");

    // If only one or zero pages exist, hide everything
    if (totalPages <= 1) {
        paginationContainer.classList.add("hidden");
        return;
    } else {
        paginationContainer.classList.remove("hidden");
    }

    pageNumbersContainer.innerHTML = "";

    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    if (endPage - startPage + 1 < maxVisiblePages) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    // Generate numbered buttons
    for (let i = startPage; i <= endPage; i++) {
        const btn = document.createElement("button");
        btn.textContent = i;
        btn.className = `px-3 py-1 rounded ${
            i === currentPage
                ? "bg-blue-600 text-white"
                : "bg-gray-200 hover:bg-gray-300"
        }`;
        btn.addEventListener("click", () => {
            currentPage = i;
            renderPublications();
        });
        pageNumbersContainer.appendChild(btn);
    }

    // Enable/disable navigation
    prevBtn.disabled = currentPage === 1;
    nextBtn.disabled = currentPage === totalPages;

    prevBtn.onclick = () => {
        if (currentPage > 1) {
            currentPage--;
            renderPublications();
        }
    };

    nextBtn.onclick = () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderPublications();
        }
    };
}

// Populate dropdowns
function populateFilterOptions() {
    const years = [...new Set(allPublications.map(pub => pub.year))].sort((a, b) => b - a);
    const topics = [...new Set(allPublications.flatMap(pub => pub.tags))].sort();

    const yearFilter = document.getElementById("yearFilter");
    const topicFilter = document.getElementById("topicFilter");

    yearFilter.innerHTML = `<option value="all">All Years</option>` + 
        years.map(y => `<option value="${y}">${y}</option>`).join("");

    topicFilter.innerHTML = topics.map(t => `<option value="${t}">${t}</option>`).join("");
}

// Filtering & search
function setupFilters() {
    const yearFilter = document.getElementById("yearFilter");
    const topicFilter = document.getElementById("topicFilter");
    const resetBtn = document.getElementById("resetFilters");
    const searchInput = document.getElementById("searchInput");

    function applyFilters() {
        const selectedYear = yearFilter.value;
        const selectedTopics = Array.from(topicFilter.selectedOptions).map(opt => opt.value.toLowerCase());
        const keyword = searchInput.value.trim().toLowerCase();

        filteredPublications = allPublications.filter(pub => {
            const matchesYear = selectedYear === "all" || pub.year.toString() === selectedYear;
            const matchesTopic = selectedTopics.length === 0 || selectedTopics.some(t => pub.tags.map(tag => tag.toLowerCase()).includes(t));
            const matchesKeyword = keyword === "" ||
                pub.title.toLowerCase().includes(keyword) ||
                pub.authors.toLowerCase().includes(keyword) ||
                pub.tags.some(tag => tag.toLowerCase().includes(keyword));

            return matchesYear && matchesTopic && matchesKeyword;
        });

        currentPage = 1;
        renderPublications();
    }

    yearFilter.addEventListener("change", applyFilters);
    topicFilter.addEventListener("change", applyFilters);
    searchInput.addEventListener("input", applyFilters);

    resetBtn.addEventListener("click", () => {
        yearFilter.value = "all";
        Array.from(topicFilter.options).forEach(opt => (opt.selected = false));
        searchInput.value = "";
        filteredPublications = [...allPublications];
        currentPage = 1;
        renderPublications();
    });
}

document.addEventListener("DOMContentLoaded", loadPublications);
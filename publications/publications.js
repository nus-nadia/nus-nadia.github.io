let allPublications = [];
let filteredPublications = [];
let currentPage = 1;
const itemsPerPage = 5;
// Topic selections live here rather than in the DOM, since the checkboxes are
// rebuilt whenever the topic list is repopulated.
const selectedTopics = new Set();

// Author strings may contain <strong> around NADIA members, so markup has to be
// removed before searching — otherwise a search for "strong" matches everything.
function plainText(value) {
    return (value || "").replace(/<[^>]+>/g, "");
}

// A link is only rendered when it actually points somewhere. Preprints have no
// DOI, and older entries use "#" as a placeholder.
function hasLink(value) {
    const url = (value || "").trim();
    return url !== "" && url !== "#";
}

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
            pubCard.dataset.authors = plainText(pub.authors).toLowerCase();

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
                        ${hasLink(pub.pdf_link) ? `<a href="${pub.pdf_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="file-text"></i> PDF</a>` : ""}
                        ${hasLink(pub.doi_link) ? `<a href="${pub.doi_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="external-link"></i> DOI</a>` : ""}
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

// Populate the year dropdown and the topic checkbox list
function populateFilterOptions() {
    const years = [...new Set(allPublications.map(pub => pub.year))].sort((a, b) => b - a);
    const topics = [...new Set(allPublications.flatMap(pub => pub.tags))].sort();

    document.getElementById("yearFilter").innerHTML =
        `<option value="all">All Years</option>` +
        years.map(y => `<option value="${y}">${y}</option>`).join("");

    document.getElementById("topicFilterMenu").innerHTML = topics.map(t => `
        <label class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-100 cursor-pointer">
            <input type="checkbox" class="topic-checkbox h-4 w-4 accent-blue-600" value="${t}">
            <span class="text-sm text-gray-700">${t}</span>
        </label>`).join("");
}

// The button doubles as the summary of what is selected, since the choices are
// hidden once the dropdown closes.
function updateTopicFilterLabel() {
    const label = document.getElementById("topicFilterLabel");
    if (selectedTopics.size === 0) {
        label.textContent = "All Topics";
    } else if (selectedTopics.size === 1) {
        label.textContent = [...selectedTopics][0];
    } else {
        label.textContent = `${selectedTopics.size} topics`;
    }
}

// Filtering & search
function setupFilters() {
    const yearFilter = document.getElementById("yearFilter");
    const topicWrapper = document.getElementById("topicFilter");
    const topicToggle = document.getElementById("topicFilterToggle");
    const topicMenu = document.getElementById("topicFilterMenu");
    const resetBtn = document.getElementById("resetFilters");
    const searchInput = document.getElementById("searchInput");

    function applyFilters() {
        const selectedYear = yearFilter.value;
        const keyword = searchInput.value.trim().toLowerCase();

        filteredPublications = allPublications.filter(pub => {
            const tags = pub.tags.map(tag => tag.toLowerCase());

            const matchesYear = selectedYear === "all" || pub.year.toString() === selectedYear;
            // Topics are OR-ed: selecting Deep Learning and Transits shows papers
            // carrying either tag, not only those carrying both.
            const matchesTopic = selectedTopics.size === 0 ||
                [...selectedTopics].some(t => tags.includes(t.toLowerCase()));
            const matchesKeyword = keyword === "" ||
                pub.title.toLowerCase().includes(keyword) ||
                plainText(pub.authors).toLowerCase().includes(keyword) ||
                tags.some(tag => tag.includes(keyword));

            return matchesYear && matchesTopic && matchesKeyword;
        });

        currentPage = 1;
        renderPublications();
    }

    function setTopicMenuOpen(open) {
        topicMenu.classList.toggle("hidden", !open);
        topicToggle.setAttribute("aria-expanded", open ? "true" : "false");
        topicToggle.querySelector(".topic-chevron").classList.toggle("rotate-180", open);
    }

    topicToggle.addEventListener("click", () => {
        setTopicMenuOpen(topicMenu.classList.contains("hidden"));
    });

    topicMenu.addEventListener("change", event => {
        const checkbox = event.target;
        if (!checkbox.classList.contains("topic-checkbox")) return;

        if (checkbox.checked) {
            selectedTopics.add(checkbox.value);
        } else {
            selectedTopics.delete(checkbox.value);
        }
        updateTopicFilterLabel();
        applyFilters();
    });

    // The dropdown has no backdrop, so it closes on an outside click or Escape.
    document.addEventListener("click", event => {
        if (!topicWrapper.contains(event.target)) setTopicMenuOpen(false);
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape") setTopicMenuOpen(false);
    });

    yearFilter.addEventListener("change", applyFilters);
    searchInput.addEventListener("input", applyFilters);

    resetBtn.addEventListener("click", () => {
        yearFilter.value = "all";
        searchInput.value = "";
        selectedTopics.clear();
        topicMenu.querySelectorAll(".topic-checkbox").forEach(box => (box.checked = false));
        updateTopicFilterLabel();
        setTopicMenuOpen(false);
        applyFilters();
    });
}

document.addEventListener("DOMContentLoaded", loadPublications);
let allJobs = [];
let filteredJobs = [];
let currentPage = 1;
const itemsPerPage = 5;
// Topic selections live here rather than in the DOM, since the checkboxes are
// rebuilt whenever the topic list is repopulated.
const selectedTopics = new Set();

// Load Jobs
async function loadJobs() {
    try {
        const response = await fetch("jobs.json");
        allJobs = await response.json();
        filteredJobs = [...allJobs];
        renderJobs();
        populateFilterOptions();
        setupFilters();
    } catch (error) {
        console.error("Error loading jobs:", error);
    }
}

// Render visible Jobs
function renderJobs() {
    const container = document.getElementById("job-list");
    container.innerHTML = "";

    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageItems = filteredJobs.slice(start, end);

    if (pageItems.length === 0) {
        container.innerHTML = `<p class="text-gray-500 text-center">No jobs at the moment! Check back again later.</p>`;
    } else {
        pageItems.forEach(job => {
            const jobCard = document.createElement("div");
            jobCard.className = "job-card bg-gray-50 p-6 rounded-lg shadow-md";
            jobCard.dataset.qualification = job.qualification;
            jobCard.dataset.topics = job.tags.join(",").toLowerCase();
            jobCard.dataset.title = job.title.toLowerCase();
            jobCard.dataset.info_text = job.info_text.toLowerCase();

            jobCard.innerHTML = `
                <div class="flex flex-col md:flex-row md:items-center md:justify-between">
                    <div class="mb-4 md:mb-0">
                        <h3 class="text-xl font-bold mb-2">${job.title}</h3>
                        <p class="text-gray-600 mb-2">${job.info_text} </p> 
                        <p class="text-gray-600 mb-2"><b>Qualifications:</b> ${job.qualification_text}</p> 
                        <div class="flex flex-wrap gap-2 mt-2">
                            ${job.tags.map(tag => `<span class="bg-blue-100 text-blue-800 text-xs px-3 py-1 rounded-full">${tag}</span>`).join("")}
                        </div>
                    </div>
                    <div class="flex space-x-4">
                        <a href="${job.job_detail_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="file-text"></i>Details</a>
                        <a href="${job.apply_link}" class="text-blue-600 hover:text-blue-800"><i data-feather="external-link"></i>Apply</a>
                    </div>
                </div>
            `;
            container.appendChild(jobCard);
        });
    }

    updatePaginationControls();
    if (typeof feather !== "undefined") feather.replace();
}

// Update pagination
function updatePaginationControls() {
    const paginationContainer = document.querySelector(".pagination-container");
    const totalPages = Math.ceil(filteredJobs.length / itemsPerPage);
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
            renderJobs();
        });
        pageNumbersContainer.appendChild(btn);
    }

    // Enable/disable navigation
    prevBtn.disabled = currentPage === 1;
    nextBtn.disabled = currentPage === totalPages;

    prevBtn.onclick = () => {
        if (currentPage > 1) {
            currentPage--;
            renderJobs();
        }
    };

    nextBtn.onclick = () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderJobs();
        }
    };
}

// Populate the qualification dropdown and the topic checkbox list
function populateFilterOptions() {
    const qualifications = [...new Set(allJobs.map(job => job.qualification))].sort();
    const topics = [...new Set(allJobs.flatMap(job => job.tags))].sort();

    document.getElementById("qualificationFilter").innerHTML =
        `<option value="all">All Qualifications</option>` +
        qualifications.map(q => `<option value="${q}">${q}</option>`).join("");

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
    const qualificationFilter = document.getElementById("qualificationFilter");
    const topicWrapper = document.getElementById("topicFilter");
    const topicToggle = document.getElementById("topicFilterToggle");
    const topicMenu = document.getElementById("topicFilterMenu");
    const resetBtn = document.getElementById("resetFilters");
    const searchInput = document.getElementById("searchInput");

    function applyFilters() {
        const selectedQualification = qualificationFilter.value;
        const keyword = searchInput.value.trim().toLowerCase();

        filteredJobs = allJobs.filter(job => {
            const tags = job.tags.map(tag => tag.toLowerCase());

            const matchesQualification = selectedQualification === "all" ||
                job.qualification.toString() === selectedQualification;
            // Topics are OR-ed: selecting Machine Learning and Exoplanets shows
            // jobs carrying either tag, not only those carrying both.
            const matchesTopic = selectedTopics.size === 0 ||
                [...selectedTopics].some(t => tags.includes(t.toLowerCase()));
            const matchesKeyword = keyword === "" ||
                job.title.toLowerCase().includes(keyword) ||
                job.info_text.toLowerCase().includes(keyword) ||
                tags.some(tag => tag.includes(keyword));

            return matchesQualification && matchesTopic && matchesKeyword;
        });

        currentPage = 1;
        renderJobs();
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

    qualificationFilter.addEventListener("change", applyFilters);
    searchInput.addEventListener("input", applyFilters);

    resetBtn.addEventListener("click", () => {
        qualificationFilter.value = "all";
        searchInput.value = "";
        selectedTopics.clear();
        topicMenu.querySelectorAll(".topic-checkbox").forEach(box => (box.checked = false));
        updateTopicFilterLabel();
        setTopicMenuOpen(false);
        applyFilters();
    });
}

document.addEventListener("DOMContentLoaded", loadJobs);
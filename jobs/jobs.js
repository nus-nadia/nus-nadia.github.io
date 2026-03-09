let allJobs = [];
let filteredJobs = [];
let currentPage = 1;
const itemsPerPage = 5;

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

// Populate dropdowns
function populateFilterOptions() {
    const qualifications = [...new Set(allJobs.map(job => job.qualification))].sort((a, b) => b - a);
    const topics = [...new Set(allJobs.flatMap(job => job.tags))].sort();

    const qualificationFilter = document.getElementById("qualificationFilter");
    const topicFilter = document.getElementById("topicFilter");

    qualificationFilter.innerHTML = `<option value="all">All qualifications</option>` + 
        qualifications.map(y => `<option value="${y}">${y}</option>`).join("");

    topicFilter.innerHTML = topics.map(t => `<option value="${t}">${t}</option>`).join("");
}

// Filtering & search
function setupFilters() {
    const qualificationFilter = document.getElementById("qualificationFilter");
    const topicFilter = document.getElementById("topicFilter");
    const resetBtn = document.getElementById("resetFilters");
    const searchInput = document.getElementById("searchInput");

    function applyFilters() {
        const selectedQualification = qualificationFilter.value;
        const selectedTopics = Array.from(topicFilter.selectedOptions).map(opt => opt.value.toLowerCase());
        const keyword = searchInput.value.trim().toLowerCase();

        filteredJobs = allJobs.filter(job => {
            const matchesQualification = selectedQualification === "all" || job.qualification.toString() === selectedQualification;
            const matchesTopic = selectedTopics.length === 0 || selectedTopics.some(t => job.tags.map(tag => tag.toLowerCase()).includes(t));
            const matchesKeyword = keyword === "" ||
                job.title.toLowerCase().includes(keyword) ||
                job.info_text.toLowerCase().includes(keyword) ||
                job.tags.some(tag => tag.toLowerCase().includes(keyword));

            return matchesQualification && matchesTopic && matchesKeyword;
        });

        currentPage = 1;
        renderJobs();
    }

    qualificationFilter.addEventListener("change", applyFilters);
    topicFilter.addEventListener("change", applyFilters);
    //searchInput.addEventListener("input", applyFilters);

    resetBtn.addEventListener("click", () => {
        qualificationFilter.value = "all";
        Array.from(topicFilter.options).forEach(opt => (opt.selected = false));
        searchInput.value = "";
        filteredJobs = [...allJobs];
        currentPage = 1;
        renderJobs();
    });
}

document.addEventListener("DOMContentLoaded", loadJobs);
/* Antiinfla-food — site script */

(function () {
  "use strict";

  /* ===== Food search data ===== */
  const foods = [
    { name: "Almond", slug: "almond", tag: "Nut" },
    { name: "Avocado", slug: "avocado", tag: "Fruit" },
    { name: "Avocado Oil", slug: "avocado-oil", tag: "Healthy Fat" },
    { name: "Basil", slug: "basil", tag: "Herb" },
    { name: "Blueberries", slug: "blueberries", tag: "Fruit" },
    { name: "Broccoli", slug: "broccoli", tag: "Vegetable" },
    { name: "Cherry", slug: "cherry", tag: "Fruit" },
    { name: "Chia Seeds", slug: "chia-seeds", tag: "Seed" },
    { name: "Chickpeas", slug: "chickpeas", tag: "Legume" },
    { name: "Cinnamon", slug: "cinnamon", tag: "Spice" },
    { name: "Flax Seeds", slug: "flax-seeds", tag: "Seed" },
    { name: "Garlic", slug: "garlic", tag: "Spice" },
    { name: "Ginger", slug: "ginger", tag: "Spice" },
    { name: "Green Tea", slug: "green-tea", tag: "Drink" },
    { name: "Kale", slug: "kale", tag: "Vegetable" },
    { name: "Lentils", slug: "lentils", tag: "Legume" },
    { name: "Matcha", slug: "matcha", tag: "Drink" },
    { name: "Oats", slug: "oats", tag: "Whole Grain" },
    { name: "Olive Oil", slug: "olive-oil", tag: "Healthy Fat" },
    { name: "Pomegranate", slug: "pomegranate", tag: "Fruit" },
    { name: "Quinoa", slug: "quinoa", tag: "Whole Grain" },
    { name: "Rosemary", slug: "rosemary", tag: "Herb" },
    { name: "Salmon", slug: "salmon", tag: "Fish" },
    { name: "Sardines", slug: "sardines", tag: "Fish" },
    { name: "Spinach", slug: "spinach", tag: "Vegetable" },
    { name: "Strawberry", slug: "strawberry", tag: "Fruit" },
    { name: "Sweet Potato", slug: "sweet-potato", tag: "Vegetable" },
    { name: "Tomato", slug: "tomato", tag: "Vegetable" },
    { name: "Turmeric", slug: "turmeric", tag: "Spice" },
    { name: "Walnut", slug: "walnut", tag: "Nut" },
  ];

  /* ===== Determine root path ===== */
  function getRootPath() {
    const path = window.location.pathname;
    if (path.match(/\/foods\/category\//)) return "../../../";
    if (path.match(/\/foods\/[^/]+\//)) return "../../";
    if (path.match(/\/guides\/[^/]+\//)) return "../../";
    return "./";
  }

  /* ===== Search ===== */
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");

  if (searchInput && searchResults) {
    const rootPath = getRootPath();

    searchInput.addEventListener("input", function () {
      const query = this.value.trim().toLowerCase();
      if (query.length < 2) {
        searchResults.classList.remove("active");
        searchResults.innerHTML = "";
        return;
      }

      const matches = foods.filter(
        (f) =>
          f.name.toLowerCase().includes(query) ||
          f.tag.toLowerCase().includes(query)
      );

      if (matches.length === 0) {
        searchResults.innerHTML =
          '<div class="search-result-item"><span>No results found</span></div>';
      } else {
        searchResults.innerHTML = matches
          .map(
            (f) =>
              `<a class="search-result-item" href="${rootPath}foods/${f.slug}/"><strong>${f.name}</strong><span>${f.tag}</span></a>`
          )
          .join("");
      }
      searchResults.classList.add("active");
    });

    // Close search results on outside click
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".search-wrapper")) {
        searchResults.classList.remove("active");
      }
    });
  }

  /* ===== Mobile menu toggle ===== */
  const menuBtn = document.getElementById("mobile-menu-btn");
  const siteNav = document.getElementById("site-nav");

  if (menuBtn && siteNav) {
    menuBtn.addEventListener("click", function () {
      siteNav.classList.toggle("open");
    });
  }
})();

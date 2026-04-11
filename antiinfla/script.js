/* Anti-inflammatory foods - site script */

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

    function getMatches(query) {
      return foods.filter(
        (f) =>
          f.name.toLowerCase().includes(query) ||
          f.tag.toLowerCase().includes(query)
      );
    }

    searchInput.addEventListener("input", function () {
      const query = this.value.trim().toLowerCase();
      if (query.length < 2) {
        searchResults.classList.remove("active");
        searchResults.innerHTML = "";
        return;
      }

      const matches = getMatches(query);

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

    searchInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") {
        return;
      }

      const query = this.value.trim().toLowerCase();
      if (query.length < 2) {
        return;
      }

      const matches = getMatches(query);
      if (matches.length === 0) {
        return;
      }

      event.preventDefault();
      window.location.href = `${rootPath}foods/${matches[0].slug}/`;
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

  /* ===== Detail image lightbox ===== */
  const detailImages = document.querySelectorAll(".detail-header-img");

  if (detailImages.length > 0) {
    const lightbox = document.createElement("div");
    lightbox.className = "image-lightbox";
    lightbox.setAttribute("aria-hidden", "true");
    lightbox.innerHTML =
      '<button class="image-lightbox-close" type="button" aria-label="Close image viewer">&times;</button><img alt="" />';

    const lightboxImg = lightbox.querySelector("img");
    const closeBtn = lightbox.querySelector(".image-lightbox-close");

    function closeLightbox() {
      lightbox.classList.remove("open");
      lightbox.setAttribute("aria-hidden", "true");
      lightboxImg.removeAttribute("src");
      lightboxImg.alt = "";
      document.body.style.overflow = "";
    }

    function openLightbox(img) {
      lightboxImg.src = img.currentSrc || img.src;
      lightboxImg.alt = img.alt || "";
      lightbox.classList.add("open");
      lightbox.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    }

    detailImages.forEach((img) => {
      img.setAttribute("tabindex", "0");
      img.setAttribute("role", "button");
      img.setAttribute("aria-label", `${img.alt || "Image"} - open larger view`);
      img.addEventListener("click", () => openLightbox(img));
      img.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openLightbox(img);
        }
      });
    });

    closeBtn.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", (event) => {
      if (event.target === lightbox) {
        closeLightbox();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && lightbox.classList.contains("open")) {
        closeLightbox();
      }
    });

    document.body.appendChild(lightbox);
  }
})();

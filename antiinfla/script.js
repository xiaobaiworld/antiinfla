/* Anti-inflammatory foods - site script */

(function () {
  "use strict";

  /* ===== Analytics ===== */
  const siteConfig = window.SITE_CONFIG || {
    gaMeasurementId: "G-QZHTKEW60L",
    googleAdsId: "",
    conversionLabels: {
      primaryCta: "",
      secondaryCta: "",
      contact: "",
    },
  };

  (function initGoogleTag() {
    const gaId = siteConfig.gaMeasurementId;
    const adsId = siteConfig.googleAdsId;

    if (
      !gaId ||
      gaId === "G-XXXXXXXXXX" ||
      typeof document === "undefined" ||
      document.querySelector(`script[src*="${gaId}"]`)
    ) {
      return;
    }

    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(gaId)}`;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
      window.dataLayer.push(arguments);
    };

    window.gtag("js", new Date());
    window.gtag("config", gaId, { anonymize_ip: true });

    if (adsId && adsId !== "AW-XXXXXXXXX") {
      window.gtag("config", adsId);
    }

    window.reportAdsConversion = function reportAdsConversion(key, url) {
      const label = siteConfig.conversionLabels && siteConfig.conversionLabels[key];
      if (!adsId || !label || typeof window.gtag !== "function") {
        if (url) {
          window.location = url;
        }
        return false;
      }

      const sendTo = `${adsId}/${label}`;
      const callback = function callback() {
        if (url) {
          window.location = url;
        }
      };

      window.gtag("event", "conversion", {
        send_to: sendTo,
        event_callback: callback,
      });

      return false;
    };
  })();

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

  const guides = [
    { name: "Best Anti-Inflammatory Foods", slug: "best-anti-inflammatory-foods", tag: "Guide" },
    { name: "Anti-Inflammatory Breakfast Ideas", slug: "anti-inflammatory-breakfast-ideas", tag: "Guide" },
    { name: "Anti-Inflammatory Drinks", slug: "anti-inflammatory-drinks", tag: "Guide" },
    { name: "Anti-Inflammatory Grocery List", slug: "anti-inflammatory-grocery-list", tag: "Guide" },
    { name: "Anti-Inflammatory Snack Ideas", slug: "anti-inflammatory-snacks", tag: "Guide" },
    { name: "Anti-Inflammatory Foods by Category", slug: "anti-inflammatory-foods-by-category", tag: "Guide" },
    { name: "How to Start an Anti-Inflammatory Diet", slug: "how-to-start-an-anti-inflammatory-diet", tag: "Guide" },
  ];

  const categories = [
    { name: "Anti-Inflammatory Fruits", slug: "fruits", tag: "Category" },
    { name: "Anti-Inflammatory Vegetables", slug: "vegetables", tag: "Category" },
    { name: "Anti-Inflammatory Spices and Herbs", slug: "spices-herbs", tag: "Category" },
    { name: "Anti-Inflammatory Nuts and Seeds", slug: "nuts-seeds", tag: "Category" },
    { name: "Anti-Inflammatory Whole Grains and Legumes", slug: "legumes-whole-grains", tag: "Category" },
    { name: "Anti-Inflammatory Healthy Fats", slug: "healthy-fats", tag: "Category" },
    { name: "Anti-Inflammatory Fish and Seafood", slug: "fish-seafood", tag: "Category" },
    { name: "Anti-Inflammatory Drink Foods", slug: "drinks", tag: "Category" },
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
    const searchItems = [
      ...foods.map((food) => ({
        name: food.name,
        tag: food.tag,
        href: `${rootPath}foods/${food.slug}/`,
      })),
      ...guides.map((guide) => ({
        name: guide.name,
        tag: guide.tag,
        href: `${rootPath}guides/${guide.slug}/`,
      })),
      ...categories.map((category) => ({
        name: category.name,
        tag: category.tag,
        href: `${rootPath}foods/category/${category.slug}/`,
      })),
    ];

    function renderResults(matches, query) {
      if (query.length < 2) {
        searchResults.classList.remove("active");
        searchResults.innerHTML = "";
        return;
      }

      if (matches.length === 0) {
        searchResults.innerHTML =
          '<div class="search-result-item"><span>No results found</span></div>';
      } else {
        searchResults.innerHTML = matches
          .map(
            (item) =>
              `<a class="search-result-item" href="${item.href}"><strong>${item.name}</strong><span>${item.tag}</span></a>`
          )
          .join("");
      }

      searchResults.classList.add("active");
    }

    function getMatches(query) {
      return searchItems.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          item.tag.toLowerCase().includes(query)
      );
    }

    searchInput.addEventListener("input", function () {
      const query = this.value.trim().toLowerCase();
      const matches = getMatches(query);
      renderResults(matches, query);
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
      window.location.href = matches[0].href;
    });

    const urlQuery = new URLSearchParams(window.location.search).get("q");
    if (urlQuery) {
      const normalizedQuery = urlQuery.trim().toLowerCase();
      searchInput.value = urlQuery.trim();
      renderResults(getMatches(normalizedQuery), normalizedQuery);
    }

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

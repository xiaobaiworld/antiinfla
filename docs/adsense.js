(function initAdSense() {
  "use strict";

  const config = window.ADSENSE_CONFIG || {};
  const publisherId = config.publisherId || "";
  const isLocalPreview = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
  const hasPublisherId = /^ca-pub-\d{16}$/.test(publisherId);

  function hidePlacement(slot) {
    const placement = slot.closest(".ad-placement");
    if (placement) {
      placement.hidden = true;
    }
  }

  function showPlaceholder(slot, slotKey) {
    if (config.previewPlaceholders === false) {
      hidePlacement(slot);
      return;
    }

    slot.classList.add("adsense-slot-preview");
    slot.innerHTML =
      '<span class="adsense-slot-label">Advertisement preview</span>' +
      "<strong>" +
      slotKey +
      "</strong>" +
      "<small>Real AdSense content appears here after the publisher and slot IDs are configured.</small>";
  }

  function renderSlots() {
    document.querySelectorAll(".adsense-slot[data-ad-slot-key]").forEach(function (slot) {
      const slotKey = slot.dataset.adSlotKey;
      const adSlotId = config.slots && config.slots[slotKey];

      if (isLocalPreview) {
        showPlaceholder(slot, slotKey);
        return;
      }

      if (!hasPublisherId || !/^\d+$/.test(adSlotId || "")) {
        hidePlacement(slot);
        return;
      }

      slot.innerHTML =
        '<ins class="adsbygoogle" style="display:block" data-ad-client="' +
        publisherId +
        '" data-ad-slot="' +
        adSlotId +
        '" data-ad-format="auto" data-full-width-responsive="true"></ins>';

      (window.adsbygoogle = window.adsbygoogle || []).push({});
    });
  }

  if (!isLocalPreview && hasPublisherId) {
    const script = document.createElement("script");
    script.async = true;
    script.crossOrigin = "anonymous";
    script.src =
      "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" +
      encodeURIComponent(publisherId);
    document.head.appendChild(script);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderSlots);
  } else {
    renderSlots();
  }
})();

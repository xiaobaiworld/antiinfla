(function initGoogleTag() {
  const config = window.SITE_CONFIG || {};
  const gaId = config.gaMeasurementId;
  const adsId = config.googleAdsId;

  if (!gaId || gaId === "G-XXXXXXXXXX") {
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
    const label = config.conversionLabels && config.conversionLabels[key];
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
      event_callback: callback
    });

    return false;
  };
})();

/* Anti-inflammatory foods - site script */

(function () {
  "use strict";

  function trackEvent(name, params) {
    if (typeof window.gtag !== "function") {
      return;
    }

    window.gtag("event", name, params || {});
  }

  function getPageType() {
    const path = window.location.pathname;

    if (/\/foods\/category\//.test(path)) return "category";
    if (/\/foods\/[^/]+\/$/.test(path)) return "food";
    if (/\/guides\/[^/]+\/$/.test(path)) return "guide";
    return "home";
  }

  function getTextLabel(element, fallback) {
    const text = (element && element.textContent ? element.textContent : fallback || "")
      .replace(/\s+/g, " ")
      .trim();
    return text || fallback || "";
  }

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
    { name: "Almond", slug: "almond", tag: "Nut", aliases: "almond almonds nut nuts snack vitamin e magnesium healthy fat crunchy topping breakfast" },
    { name: "Avocado", slug: "avocado", tag: "Fruit", aliases: "avocado fruit healthy fat lunch salad toast potassium fiber creamy" },
    { name: "Avocado Oil", slug: "avocado-oil", tag: "Healthy Fat", aliases: "avocado oil healthy fat cooking high heat saute roast dressing oil" },
    { name: "Basil", slug: "basil", tag: "Herb", aliases: "basil herb herbs pesto tomato salad flavor polyphenols fresh herb" },
    { name: "Blueberries", slug: "blueberries", tag: "Fruit", aliases: "blueberries blueberry fruit berries antioxidant anthocyanins breakfast snack yogurt oatmeal smoothie" },
    { name: "Broccoli", slug: "broccoli", tag: "Vegetable", aliases: "broccoli vegetable cruciferous fiber sulforaphane dinner side dish gut bloating cooked" },
    { name: "Cherry", slug: "cherry", tag: "Fruit", aliases: "cherry cherries fruit berries anthocyanins snack recovery dessert tart cherry" },
    { name: "Chia Seeds", slug: "chia-seeds", tag: "Seed", aliases: "chia seeds seed omega-3 omega3 ala fiber breakfast pudding smoothie yogurt snack" },
    { name: "Chickpeas", slug: "chickpeas", tag: "Legume", aliases: "chickpeas garbanzo beans legume fiber protein hummus salad bowl snack gut bloating gas" },
    { name: "Cinnamon", slug: "cinnamon", tag: "Spice", aliases: "cinnamon spice oatmeal coffee warm spice breakfast baking" },
    { name: "Flax Seeds", slug: "flax-seeds", tag: "Seed", aliases: "flax seeds flaxseed seed omega-3 omega3 ala fiber lignans smoothie oatmeal breakfast baking" },
    { name: "Garlic", slug: "garlic", tag: "Spice", aliases: "garlic spice allium savory cooking dinner soup sauce gut bloating flavor" },
    { name: "Ginger", slug: "ginger", tag: "Spice", aliases: "ginger spice tea drink nausea digestion smoothie soup stir fry" },
    { name: "Green Tea", slug: "green-tea", tag: "Drink", aliases: "green tea drink beverage polyphenols egcg antioxidant caffeine daily drink morning" },
    { name: "Kale", slug: "kale", tag: "Vegetable", aliases: "kale vegetable leafy green greens salad smoothie vitamin k fiber dinner" },
    { name: "Lentils", slug: "lentils", tag: "Legume", aliases: "lentils legume fiber protein soup bowl meal prep gut bloating gas budget" },
    { name: "Matcha", slug: "matcha", tag: "Drink", aliases: "matcha drink green tea powder egcg caffeine latte antioxidant morning" },
    { name: "Oats", slug: "oats", tag: "Whole Grain", aliases: "oats oatmeal whole grain breakfast fiber beta glucan cholesterol bowl overnight oats" },
    { name: "Olive Oil", slug: "olive-oil", tag: "Healthy Fat", aliases: "olive oil extra virgin evoo healthy fat cooking dressing salad mediterranean oleocanthal" },
    { name: "Pomegranate", slug: "pomegranate", tag: "Fruit", aliases: "pomegranate fruit antioxidant polyphenols seeds juice salad snack" },
    { name: "Quinoa", slug: "quinoa", tag: "Whole Grain", aliases: "quinoa whole grain protein bowl salad meal prep gluten free" },
    { name: "Rosemary", slug: "rosemary", tag: "Herb", aliases: "rosemary herb herbs roast potatoes chicken fish flavor polyphenols" },
    { name: "Salmon", slug: "salmon", tag: "Fish", aliases: "salmon fish seafood omega-3 omega3 epa dha protein dinner lunch fatty fish" },
    { name: "Sardines", slug: "sardines", tag: "Fish", aliases: "sardines fish seafood omega-3 omega3 epa dha calcium budget canned fish" },
    { name: "Mackerel", slug: "mackerel", tag: "Fish", aliases: "mackerel fish seafood omega-3 omega3 epa dha atlantic mackerel oily fish dinner protein" },
    { name: "Tuna", slug: "tuna", tag: "Fish", aliases: "tuna fish seafood canned tuna light tuna skipjack albacore yellowfin mercury protein lunch salad omega-3 omega3" },
    { name: "Spinach", slug: "spinach", tag: "Vegetable", aliases: "spinach vegetable leafy green greens salad smoothie folate magnesium breakfast dinner" },
    { name: "Strawberry", slug: "strawberry", tag: "Fruit", aliases: "strawberry strawberries fruit berries vitamin c breakfast snack yogurt smoothie" },
    { name: "Sweet Potato", slug: "sweet-potato", tag: "Vegetable", aliases: "sweet potato vegetable root beta carotene fiber dinner bowl meal prep" },
    { name: "Tomato", slug: "tomato", tag: "Vegetable", aliases: "tomato tomatoes vegetable fruit lycopene salad sauce cooked fresh mediterranean" },
    { name: "Turmeric", slug: "turmeric", tag: "Spice", aliases: "turmeric spice curcumin golden milk curry drink cooking ginger" },
    { name: "Walnut", slug: "walnut", tag: "Nut", aliases: "walnut walnuts nut nuts omega-3 omega3 ala snack topping breakfast salad" },
  ];

  const zhFoods = [
    { name: "杏仁", slug: "almond", tag: "坚果", aliases: "almond nut 杏仁 坚果 零食 加餐 维生素e 镁 健康脂肪" },
    { name: "牛油果", slug: "avocado", tag: "水果", aliases: "avocado fruit 牛油果 鳄梨 水果 健康脂肪 沙拉 吐司 午餐" },
    { name: "牛油果油", slug: "avocado-oil", tag: "健康脂肪", aliases: "avocado oil healthy fat 牛油果油 鳄梨油 健康脂肪 烹饪 高温 炒菜 烤菜" },
    { name: "罗勒", slug: "basil", tag: "香草", aliases: "basil herb 罗勒 香草 香草类 番茄 沙拉 调味 青酱" },
    { name: "蓝莓", slug: "blueberries", tag: "水果", aliases: "blueberries blueberry fruit 蓝莓 水果 浆果 抗氧化 花青素 早餐 零食 酸奶 燕麦 奶昔" },
    { name: "西兰花", slug: "broccoli", tag: "蔬菜", aliases: "broccoli vegetable 西兰花 蔬菜 十字花科 纤维 萝卜硫素 晚餐 腹胀 胀气" },
    { name: "樱桃", slug: "cherry", tag: "水果", aliases: "cherry fruit 樱桃 水果 浆果 花青素 零食 恢复 甜食" },
    { name: "奇亚籽", slug: "chia-seeds", tag: "种子", aliases: "chia seeds seed 奇亚籽 种子 omega-3 omega3 欧米伽3 纤维 早餐 布丁 奶昔 酸奶 零食" },
    { name: "鹰嘴豆", slug: "chickpeas", tag: "豆类", aliases: "chickpeas legume 鹰嘴豆 豆类 纤维 蛋白质 鹰嘴豆泥 沙拉 碗餐 腹胀 胀气" },
    { name: "肉桂", slug: "cinnamon", tag: "香料", aliases: "cinnamon spice 肉桂 香料 燕麦 咖啡 早餐 烘焙" },
    { name: "亚麻籽", slug: "flax-seeds", tag: "种子", aliases: "flax seeds seed 亚麻籽 种子 omega-3 omega3 欧米伽3 纤维 木酚素 奶昔 燕麦 早餐" },
    { name: "大蒜", slug: "garlic", tag: "香料", aliases: "garlic spice 大蒜 蒜 香料 调味 烹饪 晚餐 汤 酱汁 腹胀 胀气" },
    { name: "姜", slug: "ginger", tag: "香料", aliases: "ginger spice 姜 生姜 香料 姜茶 饮品 消化 奶昔 汤" },
    { name: "绿茶", slug: "green-tea", tag: "饮品", aliases: "green tea drink 绿茶 饮品 茶 多酚 egcg 抗氧化 咖啡因 日常饮品" },
    { name: "羽衣甘蓝", slug: "kale", tag: "蔬菜", aliases: "kale vegetable 羽衣甘蓝 蔬菜 绿叶菜 沙拉 奶昔 维生素k 纤维" },
    { name: "扁豆", slug: "lentils", tag: "豆类", aliases: "lentils legume 扁豆 豆类 纤维 蛋白质 汤 碗餐 备餐 腹胀 胀气" },
    { name: "抹茶", slug: "matcha", tag: "饮品", aliases: "matcha drink 抹茶 饮品 绿茶粉 egcg 咖啡因 拿铁 抗氧化" },
    { name: "燕麦", slug: "oats", tag: "全谷物", aliases: "oats whole grain 燕麦 全谷物 早餐 纤维 贝塔葡聚糖 燕麦粥 隔夜燕麦" },
    { name: "橄榄油", slug: "olive-oil", tag: "健康脂肪", aliases: "olive oil healthy fat 橄榄油 特级初榨 evoo 健康脂肪 烹饪 沙拉 地中海" },
    { name: "石榴", slug: "pomegranate", tag: "水果", aliases: "pomegranate fruit 石榴 水果 抗氧化 多酚 石榴籽 果汁 沙拉 零食" },
    { name: "藜麦", slug: "quinoa", tag: "全谷物", aliases: "quinoa whole grain 藜麦 全谷物 蛋白质 碗餐 沙拉 备餐 无麸质" },
    { name: "迷迭香", slug: "rosemary", tag: "香草", aliases: "rosemary herb 迷迭香 香草 烤菜 土豆 鸡肉 鱼 调味" },
    { name: "三文鱼", slug: "salmon", tag: "鱼类", aliases: "salmon fish 三文鱼 鱼类 海鲜 omega-3 omega3 欧米伽3 epa dha 蛋白质 晚餐 午餐 脂肪鱼" },
    { name: "沙丁鱼", slug: "sardines", tag: "鱼类", aliases: "sardines fish 沙丁鱼 鱼类 海鲜 omega-3 omega3 欧米伽3 epa dha 钙 罐头鱼" },
    { name: "鲭鱼", slug: "mackerel", tag: "鱼类", aliases: "mackerel fish 鲭鱼 青花鱼 鱼类 海鲜 omega-3 omega3 欧米伽3 epa dha 蛋白质 晚餐 脂肪鱼" },
    { name: "金枪鱼", slug: "tuna", tag: "鱼类", aliases: "tuna fish 金枪鱼 吞拿鱼 鲔鱼 鱼类 海鲜 罐装金枪鱼 淡金枪鱼 鲣鱼 长鳍金枪鱼 黄鳍金枪鱼 汞 蛋白质 午餐 沙拉 omega-3 omega3" },
    { name: "菠菜", slug: "spinach", tag: "蔬菜", aliases: "spinach vegetable 菠菜 蔬菜 绿叶菜 沙拉 奶昔 叶酸 镁 早餐 晚餐" },
    { name: "草莓", slug: "strawberry", tag: "水果", aliases: "strawberry fruit 草莓 水果 浆果 维生素c 早餐 零食 酸奶 奶昔" },
    { name: "红薯", slug: "sweet-potato", tag: "蔬菜", aliases: "sweet potato vegetable 红薯 甘薯 蔬菜 根茎 β胡萝卜素 纤维 晚餐 碗餐" },
    { name: "番茄", slug: "tomato", tag: "蔬菜", aliases: "tomato vegetable 番茄 西红柿 蔬菜 水果 番茄红素 沙拉 酱汁 熟番茄 地中海" },
    { name: "姜黄", slug: "turmeric", tag: "香料", aliases: "turmeric spice 姜黄 香料 姜黄素 黄金奶 咖喱 饮品 烹饪 生姜" },
    { name: "核桃", slug: "walnut", tag: "坚果", aliases: "walnut nut 核桃 坚果 omega-3 omega3 欧米伽3 ala 零食 早餐 沙拉" },
  ];

  const guides = [
    { name: "Best Anti-Inflammatory Foods", slug: "best-anti-inflammatory-foods", tag: "Guide", aliases: "best foods top foods anti inflammatory foods list omega-3 antioxidants fiber polyphenols where to start" },
    { name: "Anti-Inflammatory Breakfast Ideas", slug: "anti-inflammatory-breakfast-ideas", tag: "Guide", aliases: "breakfast breakfast ideas morning oatmeal oats smoothie yogurt eggs chia berries quick breakfast" },
    { name: "Anti-Inflammatory Drinks", slug: "anti-inflammatory-drinks", tag: "Guide", aliases: "drinks beverages tea green tea matcha ginger turmeric smoothie coffee hydration" },
    { name: "Anti-Inflammatory Grocery List", slug: "anti-inflammatory-grocery-list", tag: "Guide", aliases: "grocery list shopping list supermarket meal prep pantry weekly shopping budget" },
    { name: "Anti-Inflammatory Snack Ideas", slug: "anti-inflammatory-snacks", tag: "Guide", aliases: "snacks snack ideas between meals nuts berries yogurt simple snacks" },
    { name: "Anti-Inflammatory Foods by Category", slug: "anti-inflammatory-foods-by-category", tag: "Guide", aliases: "category categories fruits vegetables fish nuts seeds grains legumes healthy fats spices herbs compare foods" },
    { name: "How to Start an Anti-Inflammatory Diet", slug: "how-to-start-an-anti-inflammatory-diet", tag: "Guide", aliases: "how to start beginner first week start diet meal pattern simple steps" },
    { name: "Foods for Bloating and Gas", slug: "foods-for-bloating-and-gas", tag: "Guide", aliases: "bloating gas digestion gut stomach lentils beans broccoli garlic test foods" },
  ];

  const zhGuides = [
    { name: "最值得优先吃的抗炎食物", slug: "best-anti-inflammatory-foods", tag: "指南", aliases: "best foods 最值得吃 核心食物 抗炎食物 清单 omega-3 欧米伽3 抗氧化 纤维 多酚 从哪里开始" },
    { name: "抗炎早餐灵感", slug: "anti-inflammatory-breakfast-ideas", tag: "指南", aliases: "breakfast 早餐 早餐灵感 早饭 燕麦 奶昔 酸奶 奇亚籽 蓝莓 快手早餐" },
    { name: "抗炎饮品", slug: "anti-inflammatory-drinks", tag: "指南", aliases: "drinks 饮品 饮料 茶 绿茶 抹茶 姜茶 姜黄 奶昔 咖啡" },
    { name: "抗炎饮食购物清单", slug: "anti-inflammatory-grocery-list", tag: "指南", aliases: "grocery list 购物清单 买菜清单 超市 备餐 每周采购 食材清单" },
    { name: "抗炎零食", slug: "anti-inflammatory-snacks", tag: "指南", aliases: "snacks 零食 加餐 坚果 浆果 酸奶 简单零食" },
    { name: "按分类看抗炎食物", slug: "anti-inflammatory-foods-by-category", tag: "指南", aliases: "category 分类 水果 蔬菜 鱼 坚果 种子 全谷物 豆类 健康脂肪 香料 香草 对比食物" },
    { name: "如何开始抗炎饮食", slug: "how-to-start-an-anti-inflammatory-diet", tag: "指南", aliases: "how to start 如何开始 新手 第一周 入门 抗炎饮食 简单步骤" },
    { name: "腹胀和胀气时可以尝试的食物", slug: "foods-for-bloating-and-gas", tag: "指南", aliases: "bloating gas 腹胀 胀气 消化 肠胃 扁豆 豆类 西兰花 大蒜 测试食物" },
  ];

  const categories = [
    { name: "Anti-Inflammatory Fruits", slug: "fruits", tag: "Category", aliases: "fruit fruits berries citrus pomegranate tomatoes antioxidants anthocyanins vitamin c" },
    { name: "Anti-Inflammatory Vegetables", slug: "vegetables", tag: "Category", aliases: "vegetable vegetables greens leafy greens broccoli kale spinach tomato sweet potato fiber" },
    { name: "Anti-Inflammatory Spices and Herbs", slug: "spices-herbs", tag: "Category", aliases: "spices herbs turmeric ginger garlic cinnamon basil rosemary flavor cooking" },
    { name: "Anti-Inflammatory Nuts and Seeds", slug: "nuts-seeds", tag: "Category", aliases: "nuts seeds almonds walnuts chia flax omega-3 omega3 snack toppings" },
    { name: "Anti-Inflammatory Whole Grains and Legumes", slug: "legumes-whole-grains", tag: "Category", aliases: "whole grains legumes oats quinoa lentils chickpeas fiber protein breakfast bowls soups" },
    { name: "Anti-Inflammatory Healthy Fats", slug: "healthy-fats", tag: "Category", aliases: "healthy fats olive oil avocado avocado oil walnuts omega-3 omega3 cooking dressing" },
    { name: "Anti-Inflammatory Fish and Seafood", slug: "fish-seafood", tag: "Category", aliases: "fish seafood salmon sardines omega-3 omega3 epa dha protein dinner" },
    { name: "Anti-Inflammatory Drink Foods", slug: "drinks", tag: "Category", aliases: "drinks beverages green tea matcha ginger tea turmeric tea smoothie" },
  ];

  const zhCategories = [
    { name: "抗炎水果", slug: "fruits", tag: "分类", aliases: "fruits 水果 浆果 蓝莓 草莓 樱桃 石榴 番茄 抗氧化 花青素 维生素c" },
    { name: "抗炎蔬菜", slug: "vegetables", tag: "分类", aliases: "vegetables 蔬菜 绿叶菜 西兰花 羽衣甘蓝 菠菜 番茄 红薯 纤维" },
    { name: "抗炎香料和香草", slug: "spices-herbs", tag: "分类", aliases: "spices herbs 香料 香草 姜黄 生姜 大蒜 肉桂 罗勒 迷迭香 调味 烹饪" },
    { name: "抗炎坚果和种子", slug: "nuts-seeds", tag: "分类", aliases: "nuts seeds 坚果 种子 杏仁 核桃 奇亚籽 亚麻籽 omega-3 欧米伽3 零食" },
    { name: "抗炎全谷物和豆类", slug: "legumes-whole-grains", tag: "分类", aliases: "whole grains legumes 全谷物 豆类 燕麦 藜麦 扁豆 鹰嘴豆 纤维 蛋白质 早餐 碗餐 汤" },
    { name: "抗炎健康脂肪", slug: "healthy-fats", tag: "分类", aliases: "healthy fats 健康脂肪 橄榄油 牛油果 牛油果油 核桃 omega-3 欧米伽3 烹饪 沙拉" },
    { name: "抗炎鱼类和海鲜", slug: "fish-seafood", tag: "分类", aliases: "fish seafood 鱼类 海鲜 三文鱼 沙丁鱼 omega-3 欧米伽3 epa dha 蛋白质 晚餐" },
    { name: "抗炎饮品", slug: "drinks", tag: "分类", aliases: "drinks 饮品 饮料 绿茶 抹茶 姜茶 姜黄茶 奶昔" },
  ];

  /* ===== Determine root path ===== */
  function getRootPath() {
    const path = window.location.pathname;
    if (path.match(/\/foods\/category\//)) return "../../../";
    if (path.match(/\/foods\/[^/]+\//)) return "../../";
    if (path.match(/\/guides\/[^/]+\//)) return "../../";
    return "./";
  }

  function isChinesePage() {
    return window.location.pathname.indexOf("/zh-cn/") !== -1;
  }

  /* ===== Search ===== */
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  const heroSearchInput = document.getElementById("hero-search-input");
  const heroSearchResults = document.getElementById("hero-search-results");

  if ((searchInput && searchResults) || (heroSearchInput && heroSearchResults)) {
    const rootPath = getRootPath();
    const useChineseSearch = isChinesePage();
    const activeFoods = useChineseSearch ? zhFoods : foods;
    const activeGuides = useChineseSearch ? zhGuides : guides;
    const activeCategories = useChineseSearch ? zhCategories : categories;
    const searchItems = [
      ...activeFoods.map((food) => ({
        name: food.name,
        tag: food.tag,
        aliases: food.aliases || "",
        href: rootPath + "foods/" + food.slug + "/",
      })),
      ...activeGuides.map((guide) => ({
        name: guide.name,
        tag: guide.tag,
        aliases: guide.aliases || "",
        href: rootPath + "guides/" + guide.slug + "/",
      })),
      ...activeCategories.map((category) => ({
        name: category.name,
        tag: category.tag,
        aliases: category.aliases || "",
        href: rootPath + "foods/category/" + category.slug + "/",
      })),
    ];

    function getMatches(query) {
      return searchItems.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          item.tag.toLowerCase().includes(query) ||
          item.aliases.toLowerCase().includes(query)
      ).sort((a, b) => getMatchScore(b, query) - getMatchScore(a, query));
    }

    function getMatchScore(item, query) {
      const name = item.name.toLowerCase();
      const tag = item.tag.toLowerCase();
      const aliases = item.aliases.toLowerCase();
      const aliasWords = aliases.split(/\s+/);

      if (name === query) return 100;
      if (name.includes(query)) return 80;
      if (tag === query) return 75;
      if (aliasWords.includes(query)) return 70;
      if (tag.includes(query)) return 60;
      if (aliases.includes(query)) return 40;
      return 0;
    }

    function setupSearch(input, results) {
      if (!input || !results) {
        return;
      }

      let lastTrackedSearchTerm = "";
      let lastNoResultsTerm = "";

      function renderResults(matches, query) {
        if (query.length < 2) {
          results.classList.remove("active");
          results.innerHTML = "";
          return;
        }

        if (matches.length === 0) {
          results.innerHTML = "<div class=\"search-result-item\"><span>" + (useChineseSearch ? "没有找到结果" : "No results found") + "</span></div>";
        } else {
          results.innerHTML = matches
            .slice(0, 8)
            .map(
              (item) =>
                "<a class=\"search-result-item\" href=\"" + item.href + "\"><strong>" + item.name + "</strong><span>" + item.tag + "</span></a>"
            )
            .join("");
        }

        results.classList.add("active");
      }

      function trackSearchInput(query, matches) {
        if (query.length >= 2 && query !== lastTrackedSearchTerm) {
          trackEvent("search_input", {
            search_term: query,
            result_count: matches.length,
            page_type: getPageType(),
          });
          lastTrackedSearchTerm = query;
        }

        if (query.length >= 2 && matches.length === 0 && query !== lastNoResultsTerm) {
          trackEvent("search_no_results", {
            search_term: query,
            page_type: getPageType(),
          });
          lastNoResultsTerm = query;
        }

        if (matches.length > 0) {
          lastNoResultsTerm = "";
        }
      }

      function redirectToFirstMatch(query) {
        if (query.length < 2) {
          return false;
        }

        const matches = getMatches(query);
        if (matches.length === 0) {
          renderResults(matches, query);
          return false;
        }

        trackEvent("search_enter_redirect", {
          search_term: query,
          result_name: matches[0].name,
          result_type: matches[0].tag,
          page_type: getPageType(),
        });
        window.location.href = matches[0].href;
        return true;
      }

      input.addEventListener("input", function () {
        const query = this.value.trim().toLowerCase();
        const matches = getMatches(query);
        trackSearchInput(query, matches);
        renderResults(matches, query);
      });

      input.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") {
          return;
        }

        const query = this.value.trim().toLowerCase();
        if (redirectToFirstMatch(query)) {
          event.preventDefault();
        }
      });

      const form = input.closest("form");
      if (form) {
        form.addEventListener("submit", function (event) {
          const query = input.value.trim().toLowerCase();
          if (redirectToFirstMatch(query)) {
            event.preventDefault();
          }
        });
      }

      results.addEventListener("click", function (event) {
        const resultLink = event.target.closest(".search-result-item[href]");
        if (!resultLink) {
          return;
        }

        const resultName = getTextLabel(resultLink.querySelector("strong"), "Unknown result");
        const resultType = getTextLabel(resultLink.querySelector("span"), "Unknown");
        trackEvent("search_select", {
          search_term: input.value.trim().toLowerCase(),
          result_name: resultName,
          result_type: resultType,
          page_type: getPageType(),
        });
      });

      const urlQuery = new URLSearchParams(window.location.search).get("q");
      if (urlQuery) {
        const normalizedQuery = urlQuery.trim().toLowerCase();
        input.value = urlQuery.trim();
        renderResults(getMatches(normalizedQuery), normalizedQuery);
      }
    }

    setupSearch(searchInput, searchResults);
    setupSearch(heroSearchInput, heroSearchResults);

    // Close search results on outside click
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".search-wrapper")) {
        if (searchResults) searchResults.classList.remove("active");
        if (heroSearchResults) heroSearchResults.classList.remove("active");
      }
    });
  }

  /* ===== Mobile menu toggle ===== */
  const menuBtn = document.getElementById("mobile-menu-btn");
  const siteNav = document.getElementById("site-nav");
  const siteLogo = document.querySelector(".site-logo");

  if (menuBtn && siteNav) {
    menuBtn.addEventListener("click", function () {
      siteNav.classList.toggle("open");
      trackEvent("mobile_menu_toggle", {
        state: siteNav.classList.contains("open") ? "open" : "close",
        page_type: getPageType(),
      });
    });
  }

  if (siteLogo) {
    siteLogo.addEventListener("click", function () {
      trackEvent("nav_click", {
        nav_label: getTextLabel(siteLogo, "Logo"),
        nav_target: siteLogo.getAttribute("href") || "",
        page_type: getPageType(),
      });
    });
  }

  if (siteNav) {
    siteNav.addEventListener("click", function (event) {
      const navLink = event.target.closest("a[href]");
      if (!navLink || navLink.closest(".search-results")) {
        return;
      }

      trackEvent("nav_click", {
        nav_label: getTextLabel(navLink, "Navigation"),
        nav_target: navLink.getAttribute("href") || "",
        page_type: getPageType(),
      });
    });
  }

  /* ===== Sister site footer link ===== */
  const footerInner = document.querySelector(".site-footer .footer-inner");

  if (footerInner && !footerInner.querySelector(".footer-links.sister-site-links")) {
    const guidesBlock = Array.from(footerInner.querySelectorAll(".footer-links")).find((block) => {
      const heading = block.querySelector("h4");
      return heading && heading.textContent.trim().toLowerCase() === "guides";
    });

    const sisterBlock = document.createElement("div");
    sisterBlock.className = "footer-links sister-site-links";
    const sisterHeading = isChinesePage() ? "友好链接" : "Useful Links";
    sisterBlock.innerHTML =
      `<h4>${sisterHeading}</h4><ul><li><a href="https://www.guthealthfoods.net/en" target="_blank" rel="noopener noreferrer">Gut Health Foods</a></li></ul>`;

    if (guidesBlock && guidesBlock.nextSibling) {
      footerInner.insertBefore(sisterBlock, guidesBlock.nextSibling);
    } else {
      footerInner.appendChild(sisterBlock);
    }
  }

  const footerBottom = document.querySelector(".site-footer .footer-bottom");

  if (footerBottom) {
    const ensureFooterLink = function ensureFooterLink(href, label) {
      const existing = Array.from(footerBottom.querySelectorAll("a")).find(function (link) {
        const normalizedHref = link.getAttribute("href") || "";
        const normalizedText = (link.textContent || "").trim().toLowerCase();
        return normalizedHref === href || normalizedText === label.toLowerCase();
      });

      if (existing) {
        return;
      }

      const separator = document.createElement("span");
      separator.className = "footer-separator";
      separator.textContent = "|";

      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.textContent = label;

      footerBottom.appendChild(separator);
      footerBottom.appendChild(anchor);
    };

    ensureFooterLink("/about/", "About");
    ensureFooterLink("/contact/", "Contact");
  }

  document.addEventListener("click", function (event) {
    const clickedCard = event.target.closest(".card, .guide-card, .pill, .food-link-card");
    if (!clickedCard) {
      return;
    }

    let eventName = "content_card_click";
    let sourceSection = "unknown";

    if (clickedCard.classList.contains("card")) {
      eventName = "food_card_click";
      sourceSection = "all_foods";
    } else if (clickedCard.classList.contains("guide-card")) {
      eventName = "guide_card_click";
      sourceSection = "practical_guides";
    } else if (clickedCard.classList.contains("pill")) {
      eventName = "category_card_click";
      sourceSection = "browse_by_category";
    } else if (clickedCard.classList.contains("food-link-card")) {
      eventName = "food_card_click";
      sourceSection = "category_food_links";
    }

    trackEvent(eventName, {
      item_name: getTextLabel(
        clickedCard.querySelector("h3, strong"),
        getTextLabel(clickedCard)
      ),
      item_type: getTextLabel(clickedCard.querySelector(".card-tag"), "Link"),
      source_section: sourceSection,
      destination: clickedCard.getAttribute("href") || "",
      page_type: getPageType(),
    });
  });

  document.addEventListener("click", function (event) {
    const footerLink = event.target.closest(".site-footer a[href]");
    if (!footerLink) {
      return;
    }

    if (footerLink.closest(".sister-site-links")) {
      trackEvent("sister_site_click", {
        link_label: getTextLabel(footerLink, "Sister Site"),
        destination: footerLink.href || footerLink.getAttribute("href") || "",
        page_type: getPageType(),
      });
      return;
    }

    if (footerLink.closest(".footer-bottom")) {
      trackEvent("footer_utility_click", {
        link_label: getTextLabel(footerLink, "Footer Utility"),
        destination: footerLink.getAttribute("href") || "",
        page_type: getPageType(),
      });
    }
  });

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
      trackEvent("food_image_close", {
        image_alt: lightboxImg.alt || "",
        page_type: getPageType(),
      });
      lightbox.classList.remove("open");
      lightbox.setAttribute("aria-hidden", "true");
      lightboxImg.removeAttribute("src");
      lightboxImg.alt = "";
      document.body.style.overflow = "";
    }

    function openLightbox(img) {
      trackEvent("food_image_open", {
        image_alt: img.alt || "",
        page_type: getPageType(),
      });
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

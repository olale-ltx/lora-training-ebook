let lenis = null;
let closeMobileNav = () => {};

// Lenis smooths wheel/trackpad scrolling, matching ltx.io. It is never started
// (and is torn down again) when the reader asks for reduced motion.
const setupLenis = () => {
  if (typeof window.Lenis !== "function") return;
  const stillPreferred = window.matchMedia("(prefers-reduced-motion: reduce)");
  const start = () => {
    if (lenis || stillPreferred.matches) return;
    lenis = new window.Lenis({ autoRaf: true });
  };
  const stop = () => {
    if (!lenis) return;
    lenis.destroy();
    lenis = null;
  };
  stillPreferred.addEventListener("change", () => (stillPreferred.matches ? stop() : start()));
  start();
};

// Menu navigation is a jump, not a scroll animation. Lenis already honours the
// target's scroll-margin-top; the fallback path has to subtract it itself.
const jumpTo = (target) => {
  // The logos point at the page container, whose first child's margin collapses
  // above it, so those jumps go to the document top instead of the box top.
  const top = target.id === "top";
  if (lenis) {
    lenis.scrollTo(top ? 0 : target, { immediate: true, force: true });
    return;
  }
  if (top) {
    window.scrollTo({ top: 0, behavior: "auto" });
    return;
  }
  const margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
  window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - margin, behavior: "auto" });
};

const setupInPageJumps = () => {
  const scopes = "[data-mobile-header], .rail, .whats-inside, .hero, .back-to-top";
  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href^="#"]');
    if (!link || !link.closest(scopes)) return;
    const id = link.getAttribute("href").slice(1);
    const target = id && document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    // The open drawer locks body scrolling, so it has to go before the jump.
    closeMobileNav();
    jumpTo(target);
    history.replaceState(null, "", `#${id}`);
  });
};

const setupMobileNav = () => {
  const n = document.querySelector("[data-mobile-header]");
  if (!n) return;
  const bar = n.querySelector(".mh__bar");
  const toggle = n.querySelector("[data-mh-toggle]");
  const drawer = n.querySelector("[data-mh-drawer]");
  const scrim = n.querySelector("[data-mh-scrim]");
  const links = n.querySelectorAll("[data-mh-link]");
  const expands = n.querySelectorAll("[data-mh-expand]");
  const items = n.querySelectorAll("[data-mh-item]");
  if (!bar || !toggle || !drawer || !scrim) return;

  const setHeight = () => {
    document.documentElement.style.setProperty("--mh-height", `${Math.round(bar.getBoundingClientRect().height)}px`);
  };
  const setOpen = (open) => {
    n.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.style.overflow = open ? "hidden" : "";
  };
  const setExpanded = (id, open) => {
    const item = n.querySelector(`[data-mh-item="${id}"]`);
    const btn = n.querySelector(`[data-mh-expand="${id}"]`);
    const sections = n.querySelector(`[data-mh-sections="${id}"]`);
    if (!item) return;
    item.classList.toggle("is-expanded", open);
    btn?.setAttribute("aria-expanded", open ? "true" : "false");
    sections?.setAttribute("aria-hidden", open ? "false" : "true");
  };
  const collapseOthers = (keep) => {
    items.forEach((item) => {
      const id = item.dataset.mhItem;
      if (id && id !== keep && item.classList.contains("is-expanded")) setExpanded(id, false);
    });
  };

  closeMobileNav = () => {
    if (n.classList.contains("is-open")) setOpen(false);
  };

  toggle.addEventListener("click", () => setOpen(!n.classList.contains("is-open")));
  scrim.addEventListener("click", () => setOpen(false));
  expands.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.dataset.mhExpand;
      if (!id) return;
      const open = n.querySelector(`[data-mh-item="${id}"]`)?.classList.contains("is-expanded");
      if (open) setExpanded(id, false);
      else {
        collapseOthers(id);
        setExpanded(id, true);
      }
    });
  });
  links.forEach((link) => link.addEventListener("click", () => setTimeout(() => setOpen(false), 60)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && n.classList.contains("is-open")) setOpen(false);
  });
  setHeight();
  window.addEventListener("resize", setHeight, { passive: true });
};

const setupRail = () => {
  const items = Array.from(document.querySelectorAll(".rail__item[data-chapter]"));
  if (!items.length) return;
  const chapters = new Map();
  const sectionsByChapter = new Map();
  const sectionLinks = new Map();
  items.forEach((item) => {
    const id = item.dataset.chapter;
    const el = id && document.getElementById(id);
    if (id && el) chapters.set(id, el);
  });
  document.querySelectorAll("[data-section]").forEach((el) => {
    const ch = el.dataset.chapter;
    if (!ch) return;
    const list = sectionsByChapter.get(ch) ?? [];
    list.push(el);
    sectionsByChapter.set(ch, list);
  });
  document.querySelectorAll("[data-section-link]").forEach((el) => {
    const id = el.dataset.sectionLink;
    if (id) sectionLinks.set(id, el);
  });

  const ids = items.map((item) => item.dataset.chapter).filter((id) => chapters.has(id));

  let activeChapter = null;
  let activeSection = null;
  let ticking = false;
  // While a chapter link is being smooth-scrolled to, keep it open so the
  // chapters it passes over don't briefly steal the expanded state.
  let pinned = null;
  let pinTimer = 0;

  // Share of the chapter that has scrolled past the top of the viewport.
  const readProgress = (el) => {
    const rect = el.getBoundingClientRect();
    const scrollable = Math.max(rect.height - window.innerHeight, 1);
    return Math.max(0, Math.min(1, -rect.top / scrollable));
  };

  const update = () => {
    ticking = false;
    const line = window.innerHeight * 0.3;
    let current = null;
    let lastPassed = -1;
    ids.forEach((id, i) => {
      const rect = chapters.get(id).getBoundingClientRect();
      if (rect.top <= line && rect.bottom > line) current = id;
      if (rect.top <= line) lastPassed = i;
    });
    if (!current && lastPassed >= 0) current = ids[lastPassed];
    if (!current) current = ids[0] ?? null;
    if (pinned) {
      current = pinned;
      if (Math.abs(chapters.get(pinned).getBoundingClientRect().top) < 40) releasePin(false);
    }

    items.forEach((item) => {
      const id = item.dataset.chapter;
      const isActive = id === current;
      const el = chapters.get(id);
      item.style.setProperty("--progress", isActive && el ? String(readProgress(el)) : "0");
      item.classList.toggle("is-active", isActive);
    });

    if (current !== activeChapter) {
      sectionLinks.forEach((link) => link.classList.remove("is-active"));
      activeChapter = current;
      activeSection = null;
    }
    const sections = current ? sectionsByChapter.get(current) ?? [] : [];
    let sectionId = null;
    let best = Infinity;
    for (const section of sections) {
      const top = section.getBoundingClientRect().top;
      if (top - line > 24) continue;
      const dist = Math.abs(top - line);
      if (dist < best) {
        best = dist;
        sectionId = section.id;
      }
    }
    if (!sectionId && sections[0]) sectionId = sections[0].id;
    if (sectionId !== activeSection) {
      sectionLinks.forEach((link) => link.classList.toggle("is-active", link.dataset.sectionLink === sectionId));
      activeSection = sectionId;
    }
  };

  const onScroll = () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  };
  const releasePin = (rerun = true) => {
    if (!pinned) return;
    pinned = null;
    clearTimeout(pinTimer);
    if (rerun) update();
  };

  document.querySelectorAll("[data-chapter-link]").forEach((link) => {
    link.addEventListener("click", () => {
      const id = link.dataset.chapterLink;
      if (!chapters.has(id)) return;
      pinned = id;
      clearTimeout(pinTimer);
      pinTimer = window.setTimeout(releasePin, 2500);
      update();
    });
  });
  ["wheel", "touchstart", "keydown"].forEach((evt) =>
    window.addEventListener(evt, releasePin, { passive: true })
  );

  update();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });

  const rail = document.querySelector(".rail");
  const intro = document.querySelector(".intro") || document.querySelector(".hero, .cover");
  if (rail && intro && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      rail.classList.toggle("is-past-hero", !entry.isIntersecting);
    }, { threshold: 0 }).observe(intro);
  } else if (rail) {
    rail.classList.add("is-past-hero");
  }
};

// One chapter open at a time, and the sections grow in with the same easing as
// the desktop rail.
//
// A <details> lays its content out only once it is open, so opening has to run
// in two steps: flip open, read a style back to resolve the panel's 0fr, then
// change to 1fr in that same task so the transition has a start value. Closing
// runs the other way and only drops [open] once the collapse has played, which
// is why the summary click is handled here instead of natively.
const setupWhatsInside = () => {
  // Kept in sync with --transition-open.
  const OPEN_MS = 500;

  document.querySelectorAll(".whats-inside__list").forEach((list) => {
    const panels = [];

    list.querySelectorAll("details").forEach((item) => {
      const summary = item.querySelector("summary");
      const sections = item.querySelector(".whats-inside__sections");
      if (!summary || !sections) return;

      const panel = document.createElement("div");
      panel.className = "whats-inside__panel";
      sections.replaceWith(panel);
      panel.appendChild(sections);
      item.classList.add("is-js");

      // The state the reader last asked for. A click that lands mid-animation
      // reverses the transition from wherever it is, rather than queueing.
      let wanted = item.open;
      let timer = 0;
      // toggle fires a task late, by which time [open] can already disagree
      // with a newer click, so our own flips are marked and ignored there.
      let ours = false;

      const flip = (open) => {
        if (item.open === open) return;
        ours = true;
        item.open = open;
      };

      const set = (open) => {
        wanted = open;
        clearTimeout(timer);
        if (open) {
          panels.forEach((other) => {
            if (other.item !== item) other.set(false);
          });
          flip(true);
          void getComputedStyle(panel).gridTemplateRows;
          item.classList.add("is-open");
          return;
        }
        item.classList.remove("is-open");
        timer = window.setTimeout(() => {
          if (!wanted) flip(false);
        }, OPEN_MS);
      };

      panels.push({ item, set });

      summary.addEventListener("click", (event) => {
        event.preventDefault();
        set(!wanted);
      });
      // Anything that opens the details on its own, e.g. find-in-page.
      item.addEventListener("toggle", () => {
        if (ours) {
          ours = false;
          return;
        }
        if (item.open !== wanted) set(item.open);
      });
    });
  });
};

const CHECK_SVG =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5 10 17.5 19 6.5"></path></svg>';

const writeToClipboard = async (text) => {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (err) {
      /* fall through to the textarea fallback */
    }
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
  } catch (err) {
    /* nothing else to try */
  }
  document.body.removeChild(ta);
};

const setupCodeCopy = () => {
  document.querySelectorAll("[data-copy-code]").forEach((btn) => {
    const body = btn.closest(".code-card")?.querySelector(".code-card__body");
    if (!body) return;
    const copyIcon = btn.innerHTML;
    let busy = false;
    btn.addEventListener("click", async () => {
      if (busy) return;
      busy = true;
      await writeToClipboard((body.innerText || "").replace(/\u00a0/g, " "));
      btn.innerHTML = CHECK_SVG;
      btn.classList.add("is-copied");
      btn.setAttribute("aria-label", "Copied");
      setTimeout(() => {
        btn.innerHTML = copyIcon;
        btn.classList.remove("is-copied");
        btn.setAttribute("aria-label", "Copy code");
        busy = false;
      }, 2000);
    });
  });
};

// The hero and the six chapter covers all run the same muted loop. Only the
// footage near the viewport is left playing, so the page never decodes seven
// clips at once, and nothing plays for a reader who asks for reduced motion.
const setupCoverVideos = () => {
  const videos = Array.from(document.querySelectorAll("[data-cover-video]"));
  if (!videos.length) return;
  const stillPreferred = window.matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = window.matchMedia("(max-width: 900px)");
  const observed = "IntersectionObserver" in window;
  const nearby = new Set(observed ? [] : videos);
  // The hero ships a landscape and a portrait cut; CSS hides one of them, and
  // only the rendered one is worth decoding.
  const hidden = (video) => !video.getClientRects().length;

  const apply = (video) => {
    if (stillPreferred.matches || hidden(video)) {
      if (stillPreferred.matches) video.removeAttribute("autoplay");
      video.pause();
      return;
    }
    if (!nearby.has(video)) {
      video.pause();
      return;
    }
    if (video.preload === "none") video.preload = "auto";
    video.play().catch(() => {});
  };
  const applyAll = () => videos.forEach(apply);

  if (observed) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) nearby.add(entry.target);
          else nearby.delete(entry.target);
          apply(entry.target);
        });
      },
      { rootMargin: "300px 0px" }
    );
    videos.forEach((video) => io.observe(video));
  }
  applyAll();
  stillPreferred.addEventListener("change", applyAll);
  narrow.addEventListener("change", applyAll);
};

const setupExternalLinks = () => {
  document.querySelectorAll(".rt a[href], .synopsis a[href]").forEach((a) => {
    const href = a.getAttribute("href") || "";
    if (href.startsWith("#") || /^(mailto:|tel:|javascript:)/i.test(href)) return;
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer");
  });
};

const boot = () => {
  setupLenis();
  setupInPageJumps();
  setupMobileNav();
  setupRail();
  setupWhatsInside();
  setupCodeCopy();
  setupExternalLinks();
  setupCoverVideos();
};
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();

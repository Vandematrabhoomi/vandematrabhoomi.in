# Archived feature: Side Ad Rail + Participate CTA box

Removed from `index.html` on user request (kept blank gutter empty for now).
This file preserves the exact working code so the feature can be pasted back
in later without re-deriving it from scratch.

Live history if you'd rather restore via git: the feature was built and
refined across commits `7226152`, `5178845`, `188c148`/`d348d75`, `f0e85cc`,
and `c67d275` on `main`. `git show <hash>` on each shows the incremental diff;
this doc is the final, cumulative, working state.

## What it did

- A sticky-feeling vertical "skyscraper" ad strip (`.side-ad-rail`) floating
  in the right-hand gutter next to the content on desktop widths only
  (hidden under 769px — no room on phones).
- It used `position: absolute` (not `fixed`), so it scrolled naturally with
  the page instead of staying pinned to the viewport.
- A small JS function, `alignAdRail()`, kept its top edge lined up with
  whichever section's own in-page `.ad-banner`/`.ad-strip` was currently
  showing (News/Opinion/Live Desk each have their own), and stretched its
  height all the way down to `document.documentElement.scrollHeight` so it
  never ran out partway down a long page. It was called on load, resize,
  language toggle, section switch, and whenever Live Desk stories or the
  breaking-news ticker refreshed (all the places that can change page
  height or which ad-banner is active).
- A "Participate" CTA box (`.cta-box`) sat in the gutter directly above the
  rail (also JS-positioned, snug against the rail's top), with a pulsing
  "Click & Participate" badge and two links: Podcast/Talk Shows/Events/
  Talent Hunt (→ YouTube channel) and Raise Your Voice for Social Issues
  (→ grievance.html). On phones it reflowed into a normal in-page block
  near the top of the content instead (no side gutter to float it in).

## CSS (was inside the main `<style>` block)

```css
/* ── Side Ad Rail — one long skyscraper strip that scrolls with the page,
   top-aligned to wherever the current section's own ad-banner starts and
   stretched all the way down to the bottom of the page (both set via JS,
   see alignAdRail()) so it's never independently floating above the
   content, and never runs out of height and leaves the lower part of the
   page without an ad strip beside it. ── */
.side-ad-rail {
  position: absolute; top: 210px; right: 18px; z-index: 50;
  display: flex; flex-direction: column;
  height: 70vh; min-height: 320px;
}
.side-ad-rail .ad-strip { width: 160px; height: 100%; margin: 0; display: flex; flex-direction: column; }
.side-ad-rail .ad-banner-slot { width: 160px; flex: 1; }
.side-ad-rail .ad-ph-hi { font-size: 15px; }
.side-ad-rail .ad-ph-en { font-size: 9px; }
.side-ad-rail .ad-contact-label { font-size: 8px; }
.side-ad-rail .ad-placeholder a { font-size: 10px; }
@media (min-width: 769px) {
  .main { margin-right: 190px; }
}
@media (max-width: 768px) {
  .side-ad-rail { display: none; }
}

/* ── Participate CTA box ──────────────────────────
   Sits right above the side ad rail on desktop (top set via JS,
   see alignAdRail()); reflows to a normal in-page block on phones
   since there's no side gutter to float it in there. ── */
.cta-box {
  background: linear-gradient(155deg, var(--red) 0%, var(--red-dark) 100%);
  border-radius: 6px;
  padding: 14px 12px 12px;
  display: flex; flex-direction: column; gap: 10px;
  box-shadow: 0 3px 10px rgba(204,0,0,.35);
}
.cta-badge {
  font-family: 'Archivo', sans-serif;
  font-size: 13px; font-weight: 800; color: #fff;
  text-align: center; letter-spacing: .02em;
  background: rgba(255,255,255,.16);
  border-radius: 20px; padding: 7px 8px;
  animation: cta-pulse 1.4s ease-in-out infinite;
}
@keyframes cta-pulse {
  0%, 100% { transform: scale(1);    opacity: 1;   }
  50%      { transform: scale(1.05); opacity: .78; }
}
.cta-item {
  display: flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.32);
  border-radius: 5px; padding: 9px;
  text-decoration: none; color: #fff;
  font-family: 'Archivo', sans-serif;
  font-size: 11.5px; font-weight: 600; line-height: 1.35;
  transition: background .15s;
}
.cta-item:hover { background: rgba(255,255,255,.24); }
.cta-item-icon { font-size: 16px; flex-shrink: 0; }
@media (min-width: 769px) {
  .cta-box { position: absolute; right: 18px; width: 160px; z-index: 50; }
}
@media (max-width: 768px) {
  .cta-box { margin: 14px 14px 0; }
}
```

## HTML

Went right after `</nav>` (the navbar) and before `<!-- NEWS SECTION -->`:

```html
<!-- Participate CTA — fills the gutter above the side ad rail on desktop;
     shows inline near the top of the page on phones, where there's no
     side gutter to place it in. -->
<div class="cta-box" id="cta-box">
  <div class="cta-badge" data-hi="👉 क्लिक करें और भाग लें" data-en="👉 Click &amp; Participate">👉 क्लिक करें और भाग लें</div>
  <a class="cta-item" href="https://www.youtube.com/@vande_matrabhoomi" target="_blank" rel="noopener noreferrer">
    <span class="cta-item-icon">🎙️</span>
    <span data-hi="पॉडकास्ट • टॉक शो • इवेंट्स • टैलेंट हंट" data-en="Podcast • Talk Shows • Events • Talent Hunt">पॉडकास्ट • टॉक शो • इवेंट्स • टैलेंट हंट</span>
  </a>
  <a class="cta-item" href="grievance.html">
    <span class="cta-item-icon">📢</span>
    <span data-hi="सामाजिक मुद्दों की आवाज़ उठाएं" data-en="Raise Your Voice for Social Issues">सामाजिक मुद्दों की आवाज़ उठाएं</span>
  </a>
</div>
```

The rail itself went right after the floating grievance `.fab` button, near the
end of `<body>`:

```html
<!-- Side Ad Rail — one long floating skyscraper strip -->
<div class="side-ad-rail">
  <div class="ad-strip">
    <span class="ad-banner-label">Advertisement</span>
    <div class="ad-banner-slot">
      <div class="ad-placeholder">
        <div class="ad-ticker-inner">
          <div class="ad-ph-hi" data-hi="विज्ञापन के लिए उपलब्ध" data-en="This Space is Available for Advertisement">विज्ञापन के लिए उपलब्ध</div>
          <div class="ad-ph-en" data-hi="यहाँ अपना ब्रांड प्रमोट करें" data-en="Promote Your Brand Here">यहाँ अपना ब्रांड प्रमोट करें</div>
          <div class="ad-contact-label" data-hi="विज्ञापन हेतु संपर्क करें" data-en="Contact for Advertisement">विज्ञापन हेतु संपर्क करें</div>
          <a href="mailto:admin@vandematrabhoomi.in">admin@vandematrabhoomi.in</a>
        </div>
      </div>
    </div>
  </div>
</div>
```

## JavaScript

```js
/* ── Side ad rail alignment ────────────────────────────
   Keeps the side ad rail's top edge level with the currently
   visible section's own ad-banner (the "yellow strip"), instead
   of a hardcoded guess -- so it stays lined up no matter which
   tab is open, whether the breaking-news ticker is showing, or
   which language's text is currently reflowing the masthead.
   Also stretches the rail all the way down to the bottom of the
   page, so the ad strip runs the full length of the page instead
   of ending partway down and leaving bare space beside the rest
   of the content as the page scrolls. Finally, on desktop widths,
   sits the participate CTA box snugly right above the rail so
   there's no bare gap left between the top of the gutter and
   where the ad strip begins. ── */
function alignAdRail() {
  var rail = document.querySelector('.side-ad-rail');
  var cta  = document.querySelector('.cta-box');
  var activeSection = document.querySelector('.section.active');
  if (!rail || !activeSection) return;
  var adBanner = activeSection.querySelector('.ad-banner, .ad-strip');
  if (!adBanner) return;
  var top = adBanner.getBoundingClientRect().top + window.scrollY;
  var pageBottom = document.documentElement.scrollHeight;
  rail.style.top = top + 'px';
  rail.style.height = Math.max(pageBottom - top - 24, 320) + 'px';
  if (cta && window.innerWidth > 768) {
    cta.style.top = Math.max(top - cta.offsetHeight - 14, 12) + 'px';
  }
}
window.addEventListener('resize', alignAdRail);
window.addEventListener('load', alignAdRail);
```

Call sites (each one re-runs `alignAdRail()` after something that could change
page height or which ad-banner is visible — re-add all of these if restoring):

- End of `setSection(name)` (tab switch: News/Opinion/Live Desk)
- End of `setLang(l)` (language toggle re-renders everything)
- End of `loadBreaking()` (breaking-news ticker showing/hiding shifts everything below it)
- End of both branches (`.then`/`.catch`) in `loadStories()` (Live Desk content changes page length)
- Once directly in the init block near the bottom of the script, plus a
  `setTimeout(alignAdRail, 300)` right after it (catches late font/image reflow)

## Why it was removed

User asked to remove it for now (voice message referred to it as "spools").
No functional bug was found in it at removal time — it was working as
designed, aligned correctly, and covered the full page height. If restoring,
paste each block back to its noted location and don't forget the `.main`
margin-right in the CSS (that's what reserves the gutter space).

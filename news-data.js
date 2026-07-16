/* Vande Matrabhoomi — News Feed
   The automatic Prasar Bharati (Akashvani News) fetch has been turned off —
   the "Fetch latest news" step was removed from both GitHub Actions
   workflows (update-news.yml and morning-update.yml); fetch_news.py itself
   is kept in the repo in case this needs to be turned back on later. The
   News tabs below are now populated only by whatever is manually published
   from the Live Desk under the "News" post type (see getCatItems() /
   newsStories() in index.html). */
window.VM_NEWS = {
  "generated": null,
  "en": { "top": [], "breaking": [], "national": [], "politics": [], "world": [], "sports": [], "business": [], "entertainment": [], "lifestyle": [] },
  "hi": { "top": [], "breaking": [], "national": [], "politics": [], "world": [], "sports": [], "business": [], "entertainment": [], "lifestyle": [] }
};

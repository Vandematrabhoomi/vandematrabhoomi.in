/* Vande Matrabhoomi — News Feed
   The automatic Prasar Bharati (Akashvani News) fetch has been turned off —
   see fetch_news.py, which is no longer invoked by
   .github/workflows/update-news.yml (the file itself is kept in the repo in
   case this needs to be turned back on later). The News tabs below are now
   populated only by whatever is manually published from the Live Desk under
   the "News" post type (see getCatItems() / newsStories() in index.html). */
window.VM_NEWS = {
  "generated": null,
  "en": { "top": [], "breaking": [], "national": [], "politics": [], "world": [], "sports": [], "business": [], "entertainment": [], "lifestyle": [] },
  "hi": { "top": [], "breaking": [], "national": [], "politics": [], "world": [], "sports": [], "business": [], "entertainment": [], "lifestyle": [] }
};

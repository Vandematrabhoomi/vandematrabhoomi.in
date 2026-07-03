// ════════════════════════════════════════════════════════════
//  Vande Matrabhoomi — Subscriber + Live Desk Sheet Script
//  Paste this into Google Apps Script (script.google.com)
//  and deploy as a web app (see setup steps below).
// ════════════════════════════════════════════════════════════

var SPREADSHEET_ID     = '100YaoQj5segk4jqJ5Gscwq7mTFXzN-NPYeZldKMjdNE';
var STORIES_SHEET_NAME = 'Live Desk Stories';
var DRAFTS_SHEET_NAME  = 'Live Desk Drafts';
var SITE_URL           = 'https://vandematrabhoomi.in';

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.type === 'story')       return publishStory_(data);
    if (data.type === 'draft')       return saveDraft_(data);
    if (data.type === 'deleteDraft') return deleteDraft_(data.id);
    return addSubscriber_(data);
  } catch (err) {
    return ContentService.createTextOutput('error: ' + err.message);
  }
}

function doGet(e) {
  try {
    if (e.parameter.type === 'story') return json_(listStories_());
    if (e.parameter.type === 'draft') return json_(listDrafts_());
    return ContentService.createTextOutput('ok');
  } catch (err) {
    return json_({ error: err.message });
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ── Subscribers (existing behaviour, unchanged) ────────────────
function addSubscriber_(data) {
  var sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName('Sheet1')
    || SpreadsheetApp.openById(SPREADSHEET_ID).getActiveSheet();

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(['Timestamp', 'Name', 'Email']);
    sheet.getRange(1, 1, 1, 3).setFontWeight('bold');
  }

  var name  = (data.name  || '').trim();
  var email = (data.email || '').trim();

  var existing = sheet.getDataRange().getValues();
  for (var i = 1; i < existing.length; i++) {
    if (existing[i][2] === email) {
      return ContentService.createTextOutput('duplicate');
    }
  }

  sheet.appendRow([new Date(), name, email]);
  return ContentService.createTextOutput('ok');
}

// ── Live Desk stories (published, public) ───────────────────────
function getStoriesSheet_() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = ss.getSheetByName(STORIES_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(STORIES_SHEET_NAME);
    sheet.appendRow(['ID', 'Timestamp', 'Headline', 'Category', 'Summary', 'Body', 'MediaUrl', 'Lang']);
    sheet.getRange(1, 1, 1, 8).setFontWeight('bold');
  }
  return sheet;
}

function publishStory_(data) {
  var hl = (data.hl || '').trim();
  if (!hl) return ContentService.createTextOutput('error: headline required');

  var id   = Date.now();
  var cat  = data.cat || 'Latest';
  var sum  = data.sum || '';
  var body = data.body || '';
  var lang = data.lang || 'hi';

  // Photo/video attachments are not stored: this Google account's Apps
  // Script project can't complete incremental OAuth consent for either the
  // Drive scope or the external-request scope (UrlFetchApp), so there is
  // currently no path from here to Drive or to GitHub. Articles publish as
  // text-only until that account restriction is resolved.
  var mediaUrl = '';

  var sheet = getStoriesSheet_();
  var pubDate = new Date();
  sheet.appendRow([id, pubDate, hl, cat, sum, body, mediaUrl, lang]);

  if (data.draftId) {
    try { deleteDraftRow_(data.draftId); } catch (draftErr) { /* publish already succeeded; ignore cleanup failure */ }
  }

  return ContentService.createTextOutput('ok');
}

// `articleUrl` is generated here so the frontend has a stable share link
// immediately, but the actual static page at that URL is written by
// generate_article_pages.py running in GitHub Actions (see
// .github/workflows/update-news.yml) — Apps Script itself has no working
// path to push files to GitHub on this account (see note in publishStory_).
function listStories_() {
  var sheet = getStoriesSheet_();
  var rows  = sheet.getDataRange().getValues();
  var out   = [];
  for (var i = 1; i < rows.length; i++) {
    var r = rows[i];
    if (!r[0]) continue;
    var ts = r[1] instanceof Date ? r[1] : new Date(r[1]);
    out.push({
      id: r[0], hl: r[2], cat: r[3], sum: r[4], body: r[5], mediaUrl: r[6], lang: r[7],
      pubDate: ts.toISOString(),
      articleUrl: SITE_URL + '/a/' + r[0] + '.html'
    });
  }
  out.reverse(); // newest first
  return out;
}

// ── Live Desk drafts (admin-only, never shown to the public) ────
// Autosaved periodically while an article is being written. Upserted by
// `id` so repeated saves of the same in-progress article update one row
// instead of piling up duplicates. Removed once the article is published.
function getDraftsSheet_() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = ss.getSheetByName(DRAFTS_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(DRAFTS_SHEET_NAME);
    sheet.appendRow(['ID', 'Timestamp', 'Headline', 'Category', 'Summary', 'Body', 'Lang']);
    sheet.getRange(1, 1, 1, 7).setFontWeight('bold');
  }
  return sheet;
}

function saveDraft_(data) {
  var id = data.id || ('d' + Date.now());
  var sheet = getDraftsSheet_();
  var rows  = sheet.getDataRange().getValues();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      sheet.getRange(i + 1, 2, 1, 6).setValues([[
        new Date(), data.hl || '', data.cat || 'Latest', data.sum || '', data.body || '', data.lang || 'hi'
      ]]);
      return json_({ ok: true, id: id });
    }
  }

  sheet.appendRow([id, new Date(), data.hl || '', data.cat || 'Latest', data.sum || '', data.body || '', data.lang || 'hi']);
  return json_({ ok: true, id: id });
}

function deleteDraftRow_(id) {
  var sheet = getDraftsSheet_();
  var rows  = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      sheet.deleteRow(i + 1);
      return;
    }
  }
}

function deleteDraft_(id) {
  deleteDraftRow_(id);
  return ContentService.createTextOutput('ok');
}

function listDrafts_() {
  var sheet = getDraftsSheet_();
  var rows  = sheet.getDataRange().getValues();
  var out   = [];
  for (var i = 1; i < rows.length; i++) {
    var r = rows[i];
    if (!r[0]) continue;
    var ts = r[1] instanceof Date ? r[1] : new Date(r[1]);
    out.push({ id: r[0], hl: r[2], cat: r[3], sum: r[4], body: r[5], lang: r[6], savedAt: ts.toISOString() });
  }
  out.reverse(); // most recently edited first
  return out;
}

// ── Setup steps ──────────────────────────────────────────────
//
// 1. Go to sheets.google.com → create a new blank sheet
//    Name it "VM Subscribers" (or anything you like).
//
// 2. In that sheet: Extensions → Apps Script
//
// 3. Delete any existing code, paste this entire file, save (Ctrl+S).
//
// 4. Click Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy
//    (Reuses the existing Web app URL already in index.html.)
//
// Done — subscribers land in "Sheet1"; published Live Desk articles land in
// "Live Desk Stories". Each article gets a shareable page at
// vandematrabhoomi.in/a/<id>.html, generated by generate_article_pages.py
// (runs hourly via GitHub Actions, reading this script's public
// doGet(?type=story) endpoint) — so a freshly published article's share
// link may take up to an hour to resolve. In-progress drafts autosave to
// "Live Desk Drafts", visible only to the admin via the password-gated Live
// Desk panel, and are deleted once published.
//
// KNOWN LIMITATION: photo/video attachments on Live Desk articles are not
// stored anywhere right now. This account's Apps Script project cannot
// complete incremental OAuth consent for the Drive scope or the
// external-request scope (UrlFetchApp) — every attempt fails with either a
// broken "Sorry, unable to open the file at present" consent screen (Drive)
// or a silent "You do not have permission" exception (UrlFetchApp), with no
// authorization prompt ever appearing to approve. This looks like an
// account-level restriction rather than anything fixable in code. Until
// resolved (e.g. by trying from a different Google account), articles
// publish as text-only.

// ════════════════════════════════════════════════════════════
//  Vande Matrabhoomi — Subscriber + Live Desk Sheet Script
//  Paste this into Google Apps Script (script.google.com)
//  and deploy as a web app (see setup steps below).
// ════════════════════════════════════════════════════════════

var SPREADSHEET_ID     = '100YaoQj5segk4jqJ5Gscwq7mTFXzN-NPYeZldKMjdNE';
var STORIES_SHEET_NAME = 'Live Desk Stories';
var DRAFTS_SHEET_NAME  = 'Live Desk Drafts';
var MEDIA_SHEET_NAME   = 'Live Desk Media';
var MEDIA_CHUNK_COLS   = 8; // must match MEDIA_MAX_CHUNKS in index.html
var SITE_URL           = 'https://vandematrabhoomi.in';

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    if (data.type === 'story')       return publishStory_(data);
    if (data.type === 'draft')       return saveDraft_(data);
    if (data.type === 'deleteDraft') return deleteDraft_(data.id);
    if (data.type === 'setMediaUrl') return setMediaUrl_(data.id, data.url);
    return addSubscriber_(data);
  } catch (err) {
    return ContentService.createTextOutput('error: ' + err.message);
  }
}

function doGet(e) {
  try {
    if (e.parameter.type === 'story') return json_(listStories_());
    if (e.parameter.type === 'draft') return json_(listDrafts_());
    if (e.parameter.type === 'media') return json_(listPendingMedia_());
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
    sheet.appendRow(['ID', 'Timestamp', 'Headline', 'Category', 'Summary', 'Body', 'MediaUrl', 'Lang', 'PostType']);
    sheet.getRange(1, 1, 1, 9).setFontWeight('bold');
  } else if (sheet.getLastColumn() < 9) {
    // Sheet predates the PostType column (added for the News post type) --
    // label it now so existing rows aren't left with a blank header.
    sheet.getRange(1, 9).setValue('PostType').setFontWeight('bold');
  }
  return sheet;
}

function publishStory_(data) {
  var hl = (data.hl || '').trim();
  if (!hl) return ContentService.createTextOutput('error: headline required');

  var id    = Date.now();
  var cat   = data.cat || 'Latest';
  var sum   = data.sum || '';
  var body  = data.body || '';
  var lang  = data.lang || 'hi';
  // 'editorial' (Opinion section), 'news' (merged into the regular category
  // feeds by the frontend), or 'short' (VM Desk banner/tab).
  var ptype = data.ptype || 'editorial';

  // The photo itself can't be uploaded from here (this Apps Script project's
  // outbound calls -- DriveApp and UrlFetchApp -- are both blocked by an
  // account-level restriction; see MEDIA note below). The browser instead
  // sends the resized photo as base64 chunks, which are stored as plain
  // sheet data (a write, not an outbound call, so it isn't blocked) and
  // picked up by a GitHub Actions job that commits the real file and calls
  // back via setMediaUrl_ once it's live.
  var mediaUrl = '';

  var sheet = getStoriesSheet_();
  var pubDate = new Date();
  sheet.appendRow([id, pubDate, hl, cat, sum, body, mediaUrl, lang, ptype]);

  if (data.mediaChunks && data.mediaChunks.length) {
    try { saveMediaChunks_(id, data.mediaChunks); } catch (mediaErr) { /* publish already succeeded; photo just won't appear */ }
  }

  if (data.draftId) {
    try { deleteDraftRow_(data.draftId); } catch (draftErr) { /* publish already succeeded; ignore cleanup failure */ }
  }

  return ContentService.createTextOutput('ok');
}

// ── Live Desk media (pending photo uploads, processed by GitHub Actions) ──
function getMediaSheet_() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = ss.getSheetByName(MEDIA_SHEET_NAME);
  if (!sheet) {
    var header = ['StoryId', 'NumChunks'];
    for (var i = 0; i < MEDIA_CHUNK_COLS; i++) header.push('Chunk' + i);
    sheet = ss.insertSheet(MEDIA_SHEET_NAME);
    sheet.appendRow(header);
    sheet.getRange(1, 1, 1, header.length).setFontWeight('bold');
  }
  return sheet;
}

function saveMediaChunks_(storyId, chunks) {
  var row = [storyId, chunks.length];
  for (var i = 0; i < MEDIA_CHUNK_COLS; i++) row.push(chunks[i] || '');
  getMediaSheet_().appendRow(row);
}

// Returns every story that has pending (unprocessed) photo chunks, i.e. a
// row in the media sheet whose story still has an empty MediaUrl.
function listPendingMedia_() {
  var mediaSheet = getMediaSheet_();
  var mediaRows  = mediaSheet.getDataRange().getValues();
  var storySheet = getStoriesSheet_();
  var storyRows  = storySheet.getDataRange().getValues();

  var pendingIds = {};
  for (var i = 1; i < storyRows.length; i++) {
    if (storyRows[i][0] && !storyRows[i][6]) pendingIds[String(storyRows[i][0])] = true;
  }

  var out = [];
  for (var r = 1; r < mediaRows.length; r++) {
    var row = mediaRows[r];
    var id = row[0];
    if (!id || !pendingIds[String(id)]) continue;
    var numChunks = row[1];
    var chunks = [];
    for (var c = 0; c < numChunks; c++) chunks.push(row[2 + c] || '');
    out.push({ id: id, chunks: chunks });
  }
  return out;
}

// Called by the GitHub Actions job once it has committed the real image
// file, to record the final public URL and stop the article showing up in
// listPendingMedia_ again. Also removes the now-unneeded chunk row.
function setMediaUrl_(id, url) {
  if (!id || !url) return ContentService.createTextOutput('error: id and url required');
  var sheet = getStoriesSheet_();
  var rows  = sheet.getDataRange().getValues();
  var found = false;
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      sheet.getRange(i + 1, 7).setValue(url); // MediaUrl column
      found = true;
      break;
    }
  }
  try { deleteMediaRow_(id); } catch (err) { /* row cleanup is best-effort */ }
  return ContentService.createTextOutput(found ? 'ok' : 'error: story not found');
}

function deleteMediaRow_(id) {
  var sheet = getMediaSheet_();
  var rows  = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      sheet.deleteRow(i + 1);
      return;
    }
  }
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
    // Rows published before the PostType column existed come back with an
    // empty r[8] -- default those to 'short' (old VMShort sentinel) or
    // 'editorial', same as the frontend's own fallback, so nothing already
    // published gets miscategorised.
    var ptype = r[8] || (r[3] === 'VMShort' ? 'short' : 'editorial');
    out.push({
      id: r[0], hl: r[2], cat: r[3], sum: r[4], body: r[5], mediaUrl: r[6], lang: r[7], ptype: ptype,
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
    sheet.appendRow(['ID', 'Timestamp', 'Headline', 'Category', 'Summary', 'Body', 'Lang', 'PostType']);
    sheet.getRange(1, 1, 1, 8).setFontWeight('bold');
  } else if (sheet.getLastColumn() < 8) {
    sheet.getRange(1, 8).setValue('PostType').setFontWeight('bold');
  }
  return sheet;
}

function saveDraft_(data) {
  var id = data.id || ('d' + Date.now());
  var ptype = data.ptype || 'editorial';
  var sheet = getDraftsSheet_();
  var rows  = sheet.getDataRange().getValues();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      sheet.getRange(i + 1, 2, 1, 7).setValues([[
        new Date(), data.hl || '', data.cat || 'Latest', data.sum || '', data.body || '', data.lang || 'hi', ptype
      ]]);
      return json_({ ok: true, id: id });
    }
  }

  sheet.appendRow([id, new Date(), data.hl || '', data.cat || 'Latest', data.sum || '', data.body || '', data.lang || 'hi', ptype]);
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
    out.push({ id: r[0], hl: r[2], cat: r[3], sum: r[4], body: r[5], lang: r[6], ptype: r[7] || 'editorial', savedAt: ts.toISOString() });
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
// (runs via GitHub Actions, reading this script's public doGet(?type=story)
// endpoint) — so a freshly published article's share link may take a few
// minutes to resolve. In-progress drafts autosave to "Live Desk Drafts",
// visible only to the admin via the password-gated Live Desk panel, and are
// deleted once published.
//
// POST TYPES: every story carries a PostType column — 'editorial' (shows in
// the Opinion section), 'news' (merged by the frontend into the matching
// category's tab on the News page, sorted in by date alongside the
// auto-fetched news — see getCatItems() in index.html), or 'short' (VM Desk
// banner/tab, Category column holds the old 'VMShort' sentinel). Rows
// published before this column existed come back with it blank; listStories_
// defaults those to 'editorial' (or 'short' if Category is still 'VMShort')
// so nothing already published gets miscategorised.
//
// PHOTOS: this account's Apps Script project can't make outbound calls
// (DriveApp and UrlFetchApp both fail with a broken/silent consent screen —
// account-level restriction, not fixable in code), so this script can't
// upload a photo anywhere itself. Instead the browser resizes the photo and
// sends it as base64 chunks (see MEDIA_CHUNK_COLS / saveMediaChunks_ above),
// stored as plain sheet rows in "Live Desk Media" — that's a write, not an
// outbound call, so it isn't blocked. process_livedesk_media.py (run via the
// same GitHub Actions workflow) fetches pending chunks via doGet(?type=media),
// reassembles the file, commits it to the site repo using the Action's own
// token, and calls back here via doPost({type:'setMediaUrl'}) to record the
// final URL — so a photo appears a few minutes after publishing, same as the
// share page.

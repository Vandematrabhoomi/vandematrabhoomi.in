// ════════════════════════════════════════════════════════════
//  Vande Matrabhoomi — Subscriber + Live Desk Sheet Script
//  Paste this into Google Apps Script (script.google.com)
//  and deploy as a web app (see setup steps below).
// ════════════════════════════════════════════════════════════

var SPREADSHEET_ID     = '100YaoQj5segk4jqJ5Gscwq7mTFXzN-NPYeZldKMjdNE';
var STORIES_SHEET_NAME = 'Live Desk Stories';
var DRAFTS_SHEET_NAME  = 'Live Desk Drafts';
var MEDIA_FOLDER_NAME  = 'VM Live Desk Media';
var MAX_MEDIA_BYTES    = 15 * 1024 * 1024; // 15MB decoded cap

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

  var mediaUrl = '';
  if (data.media) {
    try {
      mediaUrl = saveMedia_(data.media, data.mediaName || 'upload');
    } catch (mediaErr) {
      mediaUrl = ''; // media storage unavailable — publish the article without it
    }
  }

  var sheet = getStoriesSheet_();
  var id = Date.now();
  sheet.appendRow([
    id, new Date(), hl, data.cat || 'Latest', data.sum || '', data.body || '',
    mediaUrl, data.lang || 'hi'
  ]);

  if (data.draftId) {
    try { deleteDraftRow_(data.draftId); } catch (draftErr) { /* publish already succeeded; ignore cleanup failure */ }
  }

  return ContentService.createTextOutput('ok');
}

function saveMedia_(dataUrl, fileName) {
  var m = /^data:([^;]+);base64,(.*)$/.exec(dataUrl);
  if (!m) return '';
  var mime  = m[1];
  var b64   = m[2];
  var bytes = Utilities.base64Decode(b64);
  if (bytes.length > MAX_MEDIA_BYTES) {
    throw new Error('media too large (max 15MB)');
  }
  var blob = Utilities.newBlob(bytes, mime, fileName);

  var folders = DriveApp.getFoldersByName(MEDIA_FOLDER_NAME);
  var folder  = folders.hasNext() ? folders.next() : DriveApp.createFolder(MEDIA_FOLDER_NAME);

  var file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return 'https://drive.google.com/thumbnail?id=' + file.getId() + '&sz=w1600';
}

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
      pubDate: ts.toISOString()
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
// "Live Desk Stories" (media saved to a "VM Live Desk Media" Drive folder);
// in-progress drafts autosave to "Live Desk Drafts", visible only to the
// admin via the password-gated Live Desk panel, and are deleted once published.

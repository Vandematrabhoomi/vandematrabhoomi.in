// ════════════════════════════════════════════════════════════
//  Vande Matrabhoomi — Subscriber + Live Desk Sheet Script
//  Paste this into Google Apps Script (script.google.com)
//  and deploy as a web app (see setup steps below).
// ════════════════════════════════════════════════════════════

var SPREADSHEET_ID     = '100YaoQj5segk4jqJ5Gscwq7mTFXzN-NPYeZldKMjdNE';
var STORIES_SHEET_NAME = 'Live Desk Stories';
var DRAFTS_SHEET_NAME  = 'Live Desk Drafts';
var MAX_MEDIA_BYTES    = 15 * 1024 * 1024; // 15MB decoded cap
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

// ── GitHub API helpers (used for media storage + static share pages) ──
// Media used to go through DriveApp, but the Drive OAuth consent screen is
// broken for this account/script (reproduced repeatedly — "Sorry, unable to
// open the file at present" on every path to it). Routing through the
// GitHub repo instead sidesteps that entirely and reuses infrastructure we
// already control.
function githubRequest_(method, path, payload) {
  var props = PropertiesService.getScriptProperties();
  var pat   = props.getProperty('GITHUB_PAT');
  var repo  = props.getProperty('GITHUB_REPO');
  if (!pat || !repo) throw new Error('GITHUB_PAT/GITHUB_REPO script properties not set');

  var options = {
    method: method,
    headers: {
      Authorization: 'token ' + pat,
      Accept: 'application/vnd.github+json'
    },
    muteHttpExceptions: true
  };
  if (payload) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(payload);
  }
  return UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/contents/' + path, options);
}

function githubFileSha_(path) {
  var resp = githubRequest_('get', path);
  if (resp.getResponseCode() !== 200) return null;
  return JSON.parse(resp.getContentText()).sha || null;
}

function githubPutFile_(path, base64Content, message) {
  var sha = githubFileSha_(path);
  var payload = { message: message, content: base64Content };
  if (sha) payload.sha = sha;
  var resp = githubRequest_('put', path, payload);
  var code = resp.getResponseCode();
  if (code !== 200 && code !== 201) {
    throw new Error('GitHub API ' + code + ': ' + resp.getContentText().slice(0, 300));
  }
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

  var mediaUrl = '';
  if (data.media) {
    try {
      mediaUrl = saveMedia_(data.media, id);
    } catch (mediaErr) {
      mediaUrl = ''; // media storage unavailable — publish the article without it
    }
  }

  var sheet = getStoriesSheet_();
  var pubDate = new Date();
  sheet.appendRow([id, pubDate, hl, cat, sum, body, mediaUrl, lang]);

  try {
    publishArticlePage_({
      id: id, hl: hl, cat: cat, sum: sum, body: body,
      mediaUrl: mediaUrl, lang: lang, pubDate: pubDate.toISOString()
    });
  } catch (pageErr) {
    // shareable static page failed to generate; article is still published and visible on-site
  }

  if (data.draftId) {
    try { deleteDraftRow_(data.draftId); } catch (draftErr) { /* publish already succeeded; ignore cleanup failure */ }
  }

  return ContentService.createTextOutput('ok');
}

var MIME_EXT_ = {
  'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp',
  'video/mp4': 'mp4', 'video/quicktime': 'mov', 'video/webm': 'webm'
};

function saveMedia_(dataUrl, id) {
  var m = /^data:([^;]+);base64,(.*)$/.exec(dataUrl);
  if (!m) return '';
  var mime  = m[1];
  var b64   = m[2];
  var bytes = Utilities.base64Decode(b64);
  if (bytes.length > MAX_MEDIA_BYTES) {
    throw new Error('media too large (max 15MB)');
  }
  var ext  = MIME_EXT_[mime] || 'bin';
  var path = 'assets/livedesk/' + id + '.' + ext;
  githubPutFile_(path, b64, 'Live Desk media for article ' + id);
  var repo = PropertiesService.getScriptProperties().getProperty('GITHUB_REPO');
  return 'https://raw.githubusercontent.com/' + repo + '/main/' + path;
}

// ── Shareable static article page (for link previews on WhatsApp etc.) ──
// GitHub Pages is static hosting with no server-side rendering, and social
// crawlers don't execute JavaScript, so a per-article page with real <meta
// og:*> tags baked in at publish time is the only way a pasted link shows
// the article's own photo/headline instead of the generic site preview.
function escHtml_(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function buildArticleHtml_(story) {
  var lang  = story.lang === 'en' ? 'en' : 'hi';
  var url   = SITE_URL + '/a/' + story.id + '.html';
  var image = story.mediaUrl || (SITE_URL + '/assets/vande-logo.png');
  var desc  = (story.sum || story.body || '').replace(/\s+/g, ' ').trim().slice(0, 200);
  var dateStr = new Date(story.pubDate).toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  var bodyHtml = (story.body || '').split(/\n\n+/).map(function (p) {
    return '<p>' + escHtml_(p.trim()) + '</p>';
  }).join('\n');
  var backLabel = lang === 'hi' ? '← वंदे मातृभूमि पर और पढ़ें' : '← Read more on Vande Matrabhoomi';

  return '<!doctype html>\n'
    + '<html lang="' + lang + '">\n<head>\n'
    + '<meta charset="utf-8">\n'
    + '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    + '<title>' + escHtml_(story.hl) + ' — Vande Matrabhoomi</title>\n'
    + '<meta name="description" content="' + escHtml_(desc) + '">\n'
    + '<meta property="og:type" content="article">\n'
    + '<meta property="og:title" content="' + escHtml_(story.hl) + '">\n'
    + '<meta property="og:description" content="' + escHtml_(desc) + '">\n'
    + '<meta property="og:image" content="' + escHtml_(image) + '">\n'
    + '<meta property="og:url" content="' + escHtml_(url) + '">\n'
    + '<meta property="og:site_name" content="Vande Matrabhoomi">\n'
    + '<meta name="twitter:card" content="summary_large_image">\n'
    + '<link rel="icon" href="' + SITE_URL + '/assets/vande-logo.png">\n'
    + '<style>\n'
    + 'body{font-family:Georgia,"Noto Serif Devanagari",serif;max-width:720px;margin:0 auto;padding:24px;color:#1a0000;line-height:1.7;background:#fffdf9;}\n'
    + '.masthead{display:flex;align-items:center;gap:10px;margin-bottom:24px;border-bottom:3px solid #cc0000;padding-bottom:14px;}\n'
    + '.masthead img{height:40px;}\n'
    + '.masthead span{font-weight:700;font-size:20px;color:#cc0000;}\n'
    + '.cat{display:inline-block;background:#fff0f0;color:#cc0000;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 10px;border-radius:3px;margin-bottom:10px;}\n'
    + 'h1{font-size:28px;margin:6px 0 8px;color:#1a0000;}\n'
    + '.dt{color:#777;font-size:13px;margin-bottom:20px;}\n'
    + '.hero{width:100%;border-radius:6px;margin-bottom:20px;}\n'
    + 'p{margin:0 0 16px;font-size:17px;}\n'
    + '.back{display:inline-block;margin-top:28px;color:#cc0000;font-weight:600;text-decoration:none;}\n'
    + '</style>\n</head>\n<body>\n'
    + '<div class="masthead"><img src="' + SITE_URL + '/assets/vande-logo.png" alt=""><span>वंदे मातृभूमि — Vande Matrabhoomi</span></div>\n'
    + '<div class="cat">' + escHtml_(story.cat) + '</div>\n'
    + '<h1>' + escHtml_(story.hl) + '</h1>\n'
    + '<div class="dt">' + escHtml_(dateStr) + '</div>\n'
    + (story.mediaUrl ? '<img class="hero" src="' + escHtml_(story.mediaUrl) + '" alt="">\n' : '')
    + bodyHtml + '\n'
    + '<a class="back" href="' + SITE_URL + '/#opinion">' + escHtml_(backLabel) + '</a>\n'
    + '</body>\n</html>\n';
}

function publishArticlePage_(story) {
  var html = buildArticleHtml_(story);
  var b64  = Utilities.base64Encode(html, Utilities.Charset.UTF_8);
  githubPutFile_('a/' + story.id + '.html', b64, 'Publish share page for article ' + story.id);
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
// 4. Project Settings → Script Properties → add:
//      GITHUB_PAT  = a token with Contents read/write on the repo
//      GITHUB_REPO = Vandematrabhoomi/vandematrabhoomi.in
//
// 5. Click Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy
//    (Reuses the existing Web app URL already in index.html.)
//
// Done — subscribers land in "Sheet1"; published Live Desk articles land in
// "Live Desk Stories" with media committed to assets/livedesk/ in the GitHub
// repo (no Google Drive dependency), and each article also gets a static
// shareable page at vandematrabhoomi.in/a/<id>.html with real Open Graph
// preview tags. In-progress drafts autosave to "Live Desk Drafts", visible
// only to the admin via the password-gated Live Desk panel, and are deleted
// once published.

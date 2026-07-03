// ════════════════════════════════════════════════════════════
//  Vande Matrabhoomi — Subscriber Sheet Script
//  Paste this into Google Apps Script (script.google.com)
//  and deploy as a web app (see setup steps below).
// ════════════════════════════════════════════════════════════

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

    // Add header row on first run
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['Timestamp', 'Name', 'Email']);
      sheet.getRange(1, 1, 1, 3).setFontWeight('bold');
    }

    var data  = JSON.parse(e.postData.contents);
    var ts    = new Date();
    var name  = (data.name  || '').trim();
    var email = (data.email || '').trim();

    // Avoid exact duplicate emails
    var existing = sheet.getDataRange().getValues();
    for (var i = 1; i < existing.length; i++) {
      if (existing[i][2] === email) {
        return ContentService.createTextOutput('duplicate');
      }
    }

    sheet.appendRow([ts, name, email]);
    return ContentService.createTextOutput('ok');

  } catch (err) {
    return ContentService.createTextOutput('error: ' + err.message);
  }
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
// 4. Click Deploy → New deployment
//    • Type: Web app
//    • Execute as: Me
//    • Who has access: Anyone
//    → Click Deploy, approve the permissions, copy the Web app URL.
//
// 5. Open  C:\Users\Arshia4\Vande Matrabhoomi News Portal\index.html
//    Find the line:   var VM_SUBSCRIBE_URL = '';
//    Paste your URL:  var VM_SUBSCRIBE_URL = 'https://script.google.com/...';
//    Save the file.
//
// Done — every new subscriber's name and email will appear in the sheet.

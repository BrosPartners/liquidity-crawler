/**
 * Web App nhận data từ crawler (push_to_sheet.py) và ghi vào Google Sheet.
 *
 * CÁCH DEPLOY (làm 1 lần):
 *  1. Mở Google Sheet "Banking AI" -> menu Extensions -> Apps Script.
 *  2. Xoá code mẫu, dán TOÀN BỘ file này vào.
 *  3. Sửa TOKEN bên dưới thành 1 chuỗi bí mật của bạn (bất kỳ, khó đoán).
 *  4. Deploy -> New deployment -> type "Web app".
 *       - Execute as: Me (email của bạn)
 *       - Who has access: Anyone
 *     -> Deploy -> Authorize -> copy "Web app URL" (dạng .../exec).
 *  5. Dán URL + TOKEN vào file config.json của crawler.
 *
 * API: POST JSON
 *   { token, sheet, header?: [...], keyCols?: [i,...], rows: [[...], ...] }
 *   - sheet: tên tab. Tự tạo nếu chưa có.
 *   - header: nếu tab trống thì ghi header này ở dòng 1.
 *   - keyCols: các cột (0-index) tạo thành khoá; dòng trùng khoá sẽ ĐÈ thay vì thêm mới
 *              (để chạy lại cùng tuần không bị lặp). Bỏ qua = luôn append.
 *   - rows: mảng các dòng.
 * Trả về: { ok, sheet, appended, updated }
 */

var TOKEN = 'DOI_TOKEN_NAY';   // <-- ĐỔI thành chuỗi bí mật của bạn

function doGet(e) {
  return _json({ ok: true, msg: 'liquidity-crawler sheet endpoint. Dùng POST để ghi.' });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var body = JSON.parse(e.postData.contents);
    if (body.token !== TOKEN) {
      return _json({ ok: false, error: 'unauthorized' });
    }
    var name = body.sheet;
    if (!name) return _json({ ok: false, error: 'missing sheet' });

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName(name);
    if (!sh) sh = ss.insertSheet(name);

    // Ghi header nếu tab trống
    if (sh.getLastRow() === 0 && body.header && body.header.length) {
      sh.getRange(1, 1, 1, body.header.length).setValues([body.header]);
    }

    var rows = body.rows || [];
    if (!rows.length) return _json({ ok: true, sheet: name, appended: 0, updated: 0 });

    var keyCols = body.keyCols || null;
    var appended = 0, updated = 0;

    if (keyCols && keyCols.length) {
      // Map khoá hiện có -> số dòng
      var lastRow = sh.getLastRow();
      var width = rows[0].length;
      var existing = {};
      if (lastRow >= 2) {
        var data = sh.getRange(2, 1, lastRow - 1, Math.max(width, sh.getLastColumn())).getValues();
        for (var i = 0; i < data.length; i++) {
          existing[_key(data[i], keyCols)] = i + 2; // số dòng thực
        }
      }
      var toAppend = [];
      for (var r = 0; r < rows.length; r++) {
        var k = _key(rows[r], keyCols);
        if (existing[k]) {
          sh.getRange(existing[k], 1, 1, rows[r].length).setValues([rows[r]]);
          updated++;
        } else {
          toAppend.push(rows[r]);
        }
      }
      if (toAppend.length) {
        sh.getRange(sh.getLastRow() + 1, 1, toAppend.length, toAppend[0].length).setValues(toAppend);
        appended = toAppend.length;
      }
    } else {
      sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
      appended = rows.length;
    }

    return _json({ ok: true, sheet: name, appended: appended, updated: updated });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function _key(row, cols) {
  var parts = [];
  for (var i = 0; i < cols.length; i++) parts.push(String(row[cols[i]]));
  return parts.join('||');
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

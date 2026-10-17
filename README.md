# Ellipse Solar CRM

A small open-source CRM for home-visit leads. The lead list and the admin page are separate. Staff sign in with a name and PIN. Records stay in a local JSON file for now, behind the server, so the browser never holds the database.

This is a new app in `ellipse-crm`. It does not replace the live Google Apps Script CRM.

## Run it

```bash
cd ellipse-crm
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

Open http://127.0.0.1:8787

Without a sheet configured, the first start creates an Admin user and writes the PIN to `data/dev-pin.txt`. That file is not committed. Three sample visits are included so the day strip and filters are visible.

## Google Sheet

Copy `sheet.example.json` to `data/sheet.json`. Set `api_url` to the Apps Script web app link and `api_key` to the private `CRM_API_KEY` stored in the script properties. That file stays off GitHub.

The script reads the spreadsheet it is bound to. Right now that is the copy of the home-visit response sheet. Moving to the main sheet means binding the same script to the main sheet. Sign in with the employee name and PIN already stored on the sheet. New PINs use the same format, so the Google CRM can use them too.

## Pages

- `/` — leads, search, status filters, the next seven visit days, call, WhatsApp, map, and visit updates
- `/admin` — create and delete employees, and the activity log. Only an admin sees this page

Sales see their own visits plus visits with no owner. Telecallers see leads where their name is the telecaller, and they can assign a visit and write a follow-up. They cannot change visit status or documents. Managers see every lead.

A repeated phone number updates the existing lead instead of creating a second one.

The repository is https://github.com/ellipsesolarofficial/ellipse-solar-crm. GitHub stores the code. The running app stays on this computer and talks to the private sheet.

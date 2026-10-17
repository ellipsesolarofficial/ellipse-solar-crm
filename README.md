# Ellipse Solar CRM

A small open-source CRM for home-visit leads. The lead list and the admin page are separate. Staff sign in with a name and PIN. Records stay in a local JSON file for now, behind the server, so the browser never holds the database.

This is a new app in `ellipse-crm`. It does not replace the live Google Apps Script CRM.

## Run it

```bash
cd ellipse-crm
python3 server.py
```

Open http://127.0.0.1:8787

The first start creates an Admin user and writes the PIN to `data/dev-pin.txt`. That file is not committed. Three sample visits are included so the day strip and filters are visible. They are labeled as samples.

## Pages

- `/` — leads, search, status filters, the next seven visit days, call, WhatsApp, map, and visit updates
- `/admin` — create and delete employees, and the activity log. Only an admin sees this page

Sales see their own visits plus visits with no owner. Telecallers see leads where their name is the telecaller, and they can assign a visit and write a follow-up. They cannot change visit status or documents. Managers see every lead.

A repeated phone number updates the existing lead instead of creating a second one.

## Google Sheets

The server is the database boundary (`store.py`). The next step is to point that module at a private Google Sheet with a service account that stays out of the public code. The sheet is not connected yet, so this copy does not read the live customer responses.

## Publish later

GitHub can store this code. It does not run the Python server. Hosting the running app comes after the code is in the repository.

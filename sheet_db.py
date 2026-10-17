"""Google Sheet database for the CRM.

The copy response sheet is selected in data/sheet.json. A service-account
key lives in data/service-account.json. Neither file is committed.
"""

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(store.DATA, 'sheet.json')
KEY_PATH = os.path.join(store.DATA, 'service-account.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

ALIASES = {
    'timestamp': ['Timestamp'],
    'customer_name': ['Customer Name'],
    'phone': ['Phone number', 'Phone Number'],
    'address': ['Address'],
    'maps_url': ['Google Maps Location Link'],
    'site_kw': ['Site Kw', 'Site kW', 'Site KW'],
    'brand': ['Brand'],
    'quoted_price': ['Quoted Price'],
    'visit_at': ['Desired Visit Date And Time', 'Desired Visit Date and Time'],
    'remarks': ['Remarks'],
    'telecaller': ['Tele-Caller Name', 'Tele Caller Name'],
    'assignee': ['Visit Assigned To'],
    'status': ['Visit Status'],
    'visit_remarks': ['Visit Remarks'],
    'next_action': ['Next Action'],
    'id': ['Lead ID'],
    'next_action_date': ['Next Action Date'],
    'next_action_assignee': ['Next Action Assigned To'],
    'updated_by': ['Last Updated By'],
    'updated_at': ['Last Updated At'],
    'documents': ['Documents'],
    'merged_into': ['Merged Into'],
}
EXTRA_HEADERS = [
    'Lead ID', 'Next Action Date', 'Next Action Assigned To',
    'Last Updated By', 'Last Updated At', 'Documents', 'Merged Into',
]
USER_HEADERS = ['Name', 'Role', 'PIN Salt', 'PIN Hash', 'Active']
ACTIVITY_HEADERS = ['Time', 'Actor', 'Lead ID', 'Event', 'Details']

_lock = threading.RLock()
_connection = None


def sheet_hash(pin, salt):
    return hashlib.sha256(('%s:%s' % (salt, pin)).encode('utf-8')).hexdigest()


def configured():
    return os.path.exists(CONFIG_PATH)


def connect():
    global _connection
    if not configured():
        return None
    if _connection is None:
        _connection = SheetDB()
    return _connection


def _column(index):
    number = index + 1
    letters = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell(tab, row, column):
    safe = str(tab).replace("'", "''")
    return "'%s'!%s%d" % (safe, _column(column), row)


def _range(tab, cells):
    safe = str(tab).replace("'", "''")
    return "'%s'!%s" % (safe, cells)


def normalize_when(value):
    """Return YYYY-MM-DD or YYYY-MM-DDTHH:MM. The original text stays when it is not a date."""
    text = str(value or '').strip()
    if not text:
        return ''
    iso = text.replace('T', ' ')
    sizes = (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d %H:%M', 16), ('%Y-%m-%d', 10))
    for pattern, size in sizes:
        try:
            parsed = datetime.strptime(iso[:size], pattern)
        except ValueError:
            continue
        if '%H' in pattern:
            return parsed.strftime('%Y-%m-%dT%H:%M')
        return parsed.strftime('%Y-%m-%d')
    months = {name: index for index, name in enumerate(
        ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
    parts = text.replace(',', ' ').split()
    if len(parts) >= 3 and parts[1][:3].lower() in months:
        day, month, year = int(parts[0]), months[parts[1][:3].lower()], int(parts[2])
        clock = _clock(parts[3] if len(parts) > 3 else '')
        return _join(year, month, day, clock)
    numeric = text.replace('-', '/').split()
    date_bits = numeric[0].split('/')
    if len(date_bits) == 3 and all(bit.isdigit() for bit in date_bits):
        first, second, year = [int(bit) for bit in date_bits]
        if year < 100:
            year += 2000
        if first > 12:
            day, month = first, second
        elif second > 12:
            month, day = first, second
        else:
            day, month = first, second
        clock = _clock(numeric[1] if len(numeric) > 1 else '')
        return _join(year, month, day, clock)
    return text


def _clock(value):
    bits = str(value or '').split(':')
    if len(bits) < 2 or not bits[0].isdigit() or not bits[1].isdigit():
        return ''
    return '%02d:%02d' % (int(bits[0]), int(bits[1]))


def _join(year, month, day, clock):
    try:
        datetime(year, month, day)
    except ValueError:
        return ''
    base = '%04d-%02d-%02d' % (year, month, day)
    return base + 'T' + clock if clock else base


class ScriptClient:
    """Talks to the copy sheet through the Apps Script already allowed to open it."""

    def __init__(self, url, key):
        self.url = url
        self.key = key

    def _post(self, body):
        import requests
        payload = dict(body)
        payload['key'] = self.key
        response = requests.post(self.url, json=payload, timeout=90)
        text = response.text.strip()
        if not text or text.startswith('<'):
            raise ValueError('The sheet connection did not answer. Publish the latest script, then try again.')
        try:
            data = response.json()
        except ValueError:
            raise ValueError('The sheet connection returned an unexpected response.')
        if isinstance(data, dict) and data.get('error'):
            raise ValueError(data['error'])
        return data

    def titles(self):
        return self._post({'action': 'titles'})['titles']

    def add_sheet(self, title, headers):
        self._post({'action': 'addSheet', 'tab': title, 'headers': headers})

    def values(self, tab):
        return self._post({'action': 'values', 'tab': tab}).get('values', [])

    def add_headers(self, tab, headers):
        return self._post({'action': 'addHeaders', 'tab': tab, 'headers': headers})['headers']

    def append(self, tab, row):
        self._post({'action': 'append', 'tab': tab, 'row': row})

    def batch(self, cells):
        if cells:
            self._post({'action': 'batch', 'cells': cells})

    def delete_row(self, tab, row_number):
        self._post({'action': 'deleteRow', 'tab': tab, 'row': row_number})


class SheetDB:
    def __init__(self):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as handle:
            config = json.load(handle)
        self.spreadsheet_id = str(config.get('spreadsheet_id') or '').strip()
        self.responses = config.get('responses_tab') or 'Form Responses 1'
        self.users_tab = config.get('users_tab') or 'CRM_Users'
        self.activity_tab = config.get('activity_tab') or 'CRM_Activity'
        self.label = config.get('label') or 'Copy of Home Visit Details Form (Responses)'
        api_url = str(config.get('api_url') or '').strip()
        api_key = str(config.get('api_key') or '').strip()
        if api_url and api_key:
            self.client = ScriptClient(api_url, api_key)
        elif os.path.exists(KEY_PATH):
            raise ValueError('Service-account mode is not active. Use the script connection in data/sheet.json.')
        else:
            raise ValueError('data/sheet.json needs api_url and api_key for the copy sheet.')
        self._snapshot = None
        self._snapshot_at = 0

    def ping(self):
        self._load(force=True)
        return {'sheet': self.label, 'leads': len(self._snapshot['leads']), 'users': len(self._snapshot['users'])}

    def authenticate(self, name, pin):
        data = self._load()
        found = next((user for user in data['users'] if store.norm(user['name']) == store.norm(name) and user['active']), None)
        if not found or sheet_hash(pin, found['salt']) != str(found['hash']).lower():
            raise ValueError('Invalid name or PIN')
        return store.public_user(found)

    def dashboard(self, user):
        data = self._load()
        leads = [store.lead_public(lead) for lead in data['leads'] if store.can_see(user, lead)]
        staff = [store.public_user(person) for person in data['users'] if person['active']]
        return {
            'today': store.today_key(),
            'user': user,
            'staff': staff,
            'statuses': store.STATUSES,
            'actions': store.ACTIONS,
            'documents': store.DOCS,
            'leads': leads,
            'source': 'Leads are read from the copy response sheet. The main sheet is not connected.',
        }

    def create_lead(self, user, fields):
        name = str(fields.get('customer_name') or '').strip()
        phone = str(fields.get('phone') or '').strip()
        if not name:
            raise ValueError('Customer name is required')
        if len(store.phone_key(phone)) < 10:
            raise ValueError('Enter a phone number with at least 10 digits')
        maps = str(fields.get('maps_url') or '').strip()
        if maps and not (maps.startswith('https://') or maps.startswith('http://')):
            raise ValueError('Map link must start with http:// or https://')
        with _lock:
            data = self._load(force=True)
            key = store.phone_key(phone)
            existing = next((lead for lead in data['leads'] if store.phone_key(lead.get('phone')) == key), None)
            if existing:
                updates = {}
                for field in ('address', 'maps_url', 'site_kw', 'brand', 'quoted_price', 'visit_at', 'telecaller', 'assignee'):
                    incoming = str(fields.get(field) or '').strip()
                    if incoming and not str(existing.get(field) or '').strip():
                        updates[field] = incoming
                remark = str(fields.get('remarks') or '').strip()
                if remark:
                    previous = str(existing.get('remarks') or '').strip()
                    extra = '[Also submitted %s] %s' % (store.now_stamp(), remark)
                    updates['remarks'] = (previous + '\n' + extra).strip() if previous else extra
                updates['updated_by'] = user['name']
                updates['updated_at'] = store.now_stamp()
                self._write_lead(existing, updates)
                self._activity(user['name'], existing['id'], 'MERGE', {'lead': existing['id']})
                self._snapshot = None
                fresh = self._load(force=True)
                lead = next(item for item in fresh['leads'] if item['id'] == existing['id'])
                return {'lead': store.lead_public(lead), 'merged': True}

            assignee = str(fields.get('assignee') or '').strip()
            if assignee:
                match = [person for person in data['users'] if person['active'] and store.names_match(assignee, person['name'])]
                if len(match) != 1:
                    raise ValueError('Unknown employee')
                assignee = match[0]['name']
            if user['role'] == 'sales' and assignee and not store.names_match(assignee, user['name']):
                raise ValueError('You can only assign a visit to yourself')
            if user['role'] == 'sales' and assignee:
                assignee = user['name']
            lead_id = self._new_lead_id(data['leads'])
            row = {header: '' for header in data['lead_headers']}
            mapping = data['lead_map']
            values = {
                'timestamp': store.now_stamp(),
                'customer_name': name,
                'phone': phone,
                'address': str(fields.get('address') or '').strip(),
                'maps_url': maps,
                'site_kw': str(fields.get('site_kw') or '').strip(),
                'brand': str(fields.get('brand') or '').strip(),
                'quoted_price': str(fields.get('quoted_price') or '').strip(),
                'visit_at': str(fields.get('visit_at') or '').replace('T', ' '),
                'remarks': str(fields.get('remarks') or '').strip(),
                'telecaller': user['name'] if user['role'] == 'telecaller' else str(fields.get('telecaller') or '').strip(),
                'assignee': assignee,
                'id': lead_id,
                'updated_by': user['name'],
                'updated_at': store.now_stamp(),
            }
            for field, value in values.items():
                column = mapping.get(field)
                header = data['lead_headers'][column] if column is not None else None
                if header:
                    row[header] = value
            body = [row.get(header, '') for header in data['lead_headers']]
            self._append(self.responses, body)
            self._activity(user['name'], lead_id, 'CREATE_LEAD', {'lead': lead_id, 'name': name})
            self._snapshot = None
            return {'lead': {'id': lead_id, 'customer_name': name, 'phone': phone, 'sample': False}, 'merged': False}

    def update_lead(self, user, lead_id, changes):
        changes = changes or {}
        with _lock:
            data = self._load(force=True)
            lead = next((item for item in data['leads'] if item['id'] == lead_id), None)
            if not lead:
                raise ValueError('Lead not found')
            if not store.can_see(user, lead):
                raise ValueError('Access denied')
            allowed = list(store.FOLLOW_FIELDS)
            if user['role'] in ('telecaller', 'sales', 'admin', 'manager'):
                allowed.extend(store.ASSIGN_FIELDS)
            if user['role'] != 'telecaller':
                allowed.extend(store.OUTCOME_FIELDS)
            updates = {}
            for key, raw in changes.items():
                if key not in allowed:
                    raise ValueError('Field not allowed: %s' % key)
                if key == 'documents':
                    picked = raw if isinstance(raw, list) else str(raw or '').split(',')
                    keys = [item.strip() for item in picked if str(item).strip()]
                    known = [item[0] for item in store.DOCS]
                    if any(item not in known for item in keys):
                        raise ValueError('Invalid document')
                    updates['documents'] = ','.join(keys)
                    continue
                value = str(raw or '').strip()[:1500]
                if key == 'status' and value and value not in store.STATUSES:
                    raise ValueError('Invalid status')
                if key == 'next_action' and value and value not in store.ACTIONS:
                    raise ValueError('Invalid action')
                if key == 'next_action_date' and value and len(normalize_when(value)) < 10:
                    raise ValueError('Invalid date')
                if key in ('assignee', 'next_action_assignee') and value:
                    match = [person for person in data['users'] if person['active'] and store.names_match(value, person['name'])]
                    if len(match) != 1:
                        raise ValueError('Unknown employee')
                    value = match[0]['name']
                if key == 'assignee' and user['role'] == 'sales' and value and not store.names_match(value, user['name']):
                    raise ValueError('You can only assign a visit to yourself')
                if key == 'visit_at':
                    value = value.replace('T', ' ')
                updates[key] = value
            updates['updated_by'] = user['name']
            updates['updated_at'] = store.now_stamp()
            self._write_lead(lead, updates)
            self._activity(user['name'], lead_id, 'UPDATE', {'lead': lead_id, 'name': lead['customer_name'], 'fields': sorted(changes.keys())})
            self._snapshot = None
            fresh = self._load(force=True)
            saved = next(item for item in fresh['leads'] if item['id'] == lead_id)
            return store.lead_public(saved)

    def list_users(self, user):
        if user['role'] != 'admin':
            raise ValueError('Only an admin can do that')
        data = self._load()
        people = []
        for person in data['users']:
            shown = store.public_user(person)
            shown['active'] = person['active']
            people.append(shown)
        return people

    def create_user(self, actor, name, role, pin):
        if actor['role'] != 'admin':
            raise ValueError('Only an admin can do that')
        name = str(name or '').strip()
        role = str(role or '').strip()
        if not name:
            raise ValueError('Name is required')
        if role not in store.ROLES:
            raise ValueError('Invalid role')
        store.check_pin_rules(pin)
        with _lock:
            data = self._load(force=True)
            if any(store.norm(person['name']) == store.norm(name) for person in data['users']):
                raise ValueError('That name is already used')
            salt = secrets.token_hex(16)
            self._append(self.users_tab, [name, role, salt, sheet_hash(pin, salt), 'TRUE'])
            self._activity(actor['name'], '', 'CREATE_USER', {'name': name, 'role': role})
            self._snapshot = None
            return {'id': name, 'name': name, 'role': role}

    def delete_user(self, actor, user_id):
        if actor['role'] != 'admin':
            raise ValueError('Only an admin can do that')
        with _lock:
            data = self._load(force=True)
            person = next((item for item in data['users'] if item['id'] == user_id or item['name'] == user_id), None)
            if not person:
                raise ValueError('Employee not found')
            if person['name'] == actor['name']:
                raise ValueError('You cannot delete your own sign-in')
            admins = [item for item in data['users'] if item['role'] == 'admin' and item['active']]
            if person['role'] == 'admin' and len(admins) <= 1:
                raise ValueError('Keep at least one admin')
            self._delete_row(self.users_tab, person['row'])
            self._activity(actor['name'], '', 'DELETE_USER', {'name': person['name'], 'role': person['role']})
            self._snapshot = None
            return True

    def activity_for(self, user):
        if user['role'] != 'admin':
            raise ValueError('Only an admin can do that')
        data = self._load()
        return list(reversed(data['activity'][-40:]))

    def _new_lead_id(self, leads):
        used = {lead['id'] for lead in leads}
        while True:
            item_id = 'EL-' + secrets.token_hex(4).upper()
            if item_id not in used:
                return item_id

    def _write_lead(self, lead, updates):
        cells = []
        for field, value in updates.items():
            column = lead['columns'].get(field)
            if column is None:
                continue
            cells.append({'tab': self.responses, 'row': lead['row'], 'col': column + 1, 'value': value})
        self.client.batch(cells)

    def _activity(self, actor, lead_id, event, details):
        self._append(self.activity_tab, [store.now_stamp(), actor, lead_id, event, json.dumps(details)])

    def _load(self, force=False):
        if self._snapshot and not force and (datetime.now() - self._snapshot_at).total_seconds() < 20:
            return self._snapshot
        with _lock:
            if self._snapshot and not force and (datetime.now() - self._snapshot_at).total_seconds() < 20:
                return self._snapshot
            self._ensure_tabs()
            lead_headers, lead_rows = self._table(self.responses)
            lead_headers = self._ensure_headers(self.responses, lead_headers, EXTRA_HEADERS)
            user_headers, user_rows = self._table(self.users_tab)
            activity_headers, activity_rows = self._table(self.activity_tab)
            lead_map = self._map_headers(lead_headers)
            leads = []
            for row_number, values in lead_rows:
                lead = self._lead_from_row(lead_map, values, row_number)
                if lead and not str(lead.get('merged_into') or '').strip():
                    if lead.get('customer_name') or store.phone_key(lead.get('phone')):
                        leads.append(lead)
            users = []
            name_at = self._header_index(user_headers, 'Name')
            role_at = self._header_index(user_headers, 'Role')
            salt_at = self._header_index(user_headers, 'PIN Salt')
            hash_at = self._header_index(user_headers, 'PIN Hash')
            active_at = self._header_index(user_headers, 'Active')
            for row_number, values in user_rows:
                name = self._at(values, name_at)
                if not name:
                    continue
                users.append({
                    'id': name,
                    'row': row_number,
                    'name': name,
                    'role': self._at(values, role_at).lower(),
                    'salt': self._at(values, salt_at),
                    'hash': self._at(values, hash_at),
                    'active': self._at(values, active_at).lower() != 'false',
                })
            activity = []
            for row_number, values in activity_rows:
                details = self._at(values, 4)
                try:
                    parsed = json.loads(details) if details.startswith('{') or details.startswith('[') else {'text': details}
                except ValueError:
                    parsed = {'text': details}
                activity.append({
                    'time': self._at(values, 0),
                    'actor': self._at(values, 1),
                    'event': self._at(values, 3),
                    'details': parsed,
                })
            self._snapshot = {
                'leads': leads,
                'users': users,
                'activity': activity,
                'lead_headers': lead_headers,
                'lead_map': lead_map,
            }
            self._snapshot_at = datetime.now()
            return self._snapshot

    def _lead_from_row(self, mapping, values, row_number):
        lead = {'row': row_number, 'columns': mapping, 'sample': False, 'documents': []}
        for field, column in mapping.items():
            text = self._at(values, column)
            if field in ('visit_at', 'next_action_date', 'timestamp', 'updated_at'):
                normalized = normalize_when(text)
                lead[field] = normalized or text
            elif field == 'documents':
                lead[field] = [item.strip() for item in text.split(',') if item.strip()]
            else:
                lead[field] = text
        if not lead.get('id'):
            lead['id'] = 'row-%d' % row_number
        return lead

    def _map_headers(self, headers):
        mapping = {}
        for field, names in ALIASES.items():
            for name in names:
                if name in headers:
                    mapping[field] = headers.index(name)
                    break
        return mapping

    def _header_index(self, headers, name):
        return headers.index(name) if name in headers else None

    def _at(self, values, index):
        if index is None or index >= len(values):
            return ''
        return str(values[index] or '').strip()

    def _ensure_tabs(self):
        titles = self.client.titles()
        for title, headers in ((self.users_tab, USER_HEADERS), (self.activity_tab, ACTIVITY_HEADERS)):
            if title not in titles:
                self.client.add_sheet(title, headers)

    def _ensure_headers(self, tab, headers, required):
        missing = [header for header in required if header not in headers]
        if not missing:
            return headers
        return self.client.add_headers(tab, missing)

    def _table(self, tab):
        values = self.client.values(tab)
        if not values:
            return [], []
        headers = [str(header).strip() for header in values[0]]
        rows = []
        for offset, raw in enumerate(values[1:], start=2):
            padded = list(raw) + [''] * max(0, len(headers) - len(raw))
            rows.append((offset, padded[:len(headers)]))
        return headers, rows

    def _append(self, tab, row):
        self.client.append(tab, row)

    def _delete_row(self, tab, row_number):
        self.client.delete_row(tab, row_number)

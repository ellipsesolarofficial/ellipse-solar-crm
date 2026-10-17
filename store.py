"""Local JSON database for the open-source CRM.

The sheet stays out of the browser. This module is the backend boundary:
screens talk to it, and a Google Sheet adapter can replace the file later
without changing the pages.
"""

import hashlib
import json
import os
import secrets
import threading
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
DB_PATH = os.path.join(DATA, 'db.json')
PIN_PATH = os.path.join(DATA, 'dev-pin.txt')

STATUSES = [
    'Lost',
    'Visit Done',
    'Customer Not Responding',
    'Visit Pending',
    'Visit Re-Schedule',
    'Converted (Docs. Received)',
    'Need Some More Effort',
    'Visit Done (follow up)',
]
ACTIONS = [
    'Follow-up Call',
    'Second Visit',
    'Quotation Needed',
    'Family Discussion',
    'Loan / Finance Discussion',
    'Price Negotiation',
    'Ready To Process',
    'Lost',
]
DOCS = [
    ['aadhaar', 'Aadhaar'],
    ['bill', 'Electricity bill'],
    ['photos', 'Roof / site photos'],
    ['cheque', 'Cancelled cheque'],
    ['agreement', 'Signed agreement'],
]
ROLES = ['admin', 'manager', 'sales', 'telecaller']
CLOSED = ['Lost', 'Ready To Process']
CONVERTED = 'Converted (Docs. Received)'
FOLLOW_FIELDS = [
    'visit_remarks', 'next_action', 'next_action_date', 'next_action_assignee', 'visit_at',
]
ASSIGN_FIELDS = ['assignee']
OUTCOME_FIELDS = ['status', 'documents']

_lock = threading.Lock()


def now_stamp():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ', timespec='minutes')


def today_key():
    return date.today().isoformat()


def norm(value):
    return str(value or '').strip().lower()


def phone_key(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ''


def tokens(value):
    cleaned = ''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in norm(value))
    return [part for part in cleaned.split() if part and part != 'ji' and len(part) >= 2]


def names_match(left, right):
    if not norm(left) or not norm(right):
        return False
    if norm(left) == norm(right):
        return True
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return False
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    return all(token in larger for token in smaller)


def check_pin_rules(pin):
    pin = str(pin or '')
    if len(pin) < 8 or len(pin) > 12 or not pin.isdigit():
        raise ValueError('PIN must be 8–12 digits')
    if pin in ('12345678', '00000000') or len(set(pin)) == 1:
        raise ValueError('Choose a less obvious PIN')


def hash_pin(pin, salt):
    return hashlib.pbkdf2_hmac('sha256', str(pin).encode(), str(salt).encode(), 120000).hex()


def _blank():
    return {'users': [], 'leads': [], 'activity': []}


def _read():
    if not os.path.exists(DB_PATH):
        return _blank()
    with open(DB_PATH, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    data.setdefault('users', [])
    data.setdefault('leads', [])
    data.setdefault('activity', [])
    return data


def _write(data):
    os.makedirs(DATA, exist_ok=True)
    temporary = DB_PATH + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)
    os.replace(temporary, DB_PATH)


def _new_pin():
    while True:
        pin = '%08d' % (secrets.randbelow(90000000) + 10000000)
        try:
            check_pin_rules(pin)
        except ValueError:
            continue
        return pin


def _sample_leads(admin_name):
    today = date.today()

    def day(offset, hour, minute):
        return '%sT%02d:%02d' % ((today + timedelta(days=offset)).isoformat(), hour, minute)

    return [
        {
            'id': 'EL-SAMPLE01',
            'sample': True,
            'created_at': now_stamp(),
            'customer_name': 'Riverside Sample',
            'phone': '9000000011',
            'address': 'Sample lane, Jaipur',
            'maps_url': 'https://maps.google.com/?q=Jaipur',
            'site_kw': '3',
            'brand': 'Adani',
            'quoted_price': '240000',
            'visit_at': day(0, 16, 0),
            'remarks': 'Sample enquiry so the filters have something to show.',
            'telecaller': admin_name,
            'assignee': admin_name,
            'status': 'Visit Pending',
            'visit_remarks': 'Asked for a evening visit.',
            'next_action': 'Follow-up Call',
            'next_action_date': (today - timedelta(days=1)).isoformat(),
            'next_action_assignee': admin_name,
            'documents': [],
            'updated_by': 'System',
            'updated_at': now_stamp(),
        },
        {
            'id': 'EL-SAMPLE02',
            'sample': True,
            'created_at': now_stamp(),
            'customer_name': 'Canal Road Sample',
            'phone': '9000000022',
            'address': 'Sample street, Ajmer',
            'maps_url': '',
            'site_kw': '5',
            'brand': 'Tata',
            'quoted_price': '510000',
            'visit_at': day(1, 11, 30),
            'remarks': '',
            'telecaller': admin_name,
            'assignee': '',
            'status': 'Visit Re-Schedule',
            'visit_remarks': '',
            'next_action': 'Second Visit',
            'next_action_date': today.isoformat(),
            'next_action_assignee': admin_name,
            'documents': [],
            'updated_by': 'System',
            'updated_at': now_stamp(),
        },
        {
            'id': 'EL-SAMPLE03',
            'sample': True,
            'created_at': now_stamp(),
            'customer_name': 'Old City Sample',
            'phone': '9000000033',
            'address': 'Sample house, Sikar',
            'maps_url': '',
            'site_kw': '4',
            'brand': 'Waaree',
            'quoted_price': '3.6 lakh',
            'visit_at': day(-4, 10, 0),
            'remarks': '',
            'telecaller': '',
            'assignee': admin_name,
            'status': CONVERTED,
            'visit_remarks': 'Agreement pending the cheque copy.',
            'next_action': '',
            'next_action_date': '',
            'next_action_assignee': '',
            'documents': ['aadhaar', 'bill'],
            'updated_by': 'System',
            'updated_at': now_stamp(),
        },
    ]


def ensure_seed():
    with _lock:
        data = _read()
        if data['users']:
            return
        pin = _new_pin()
        salt = secrets.token_hex(16)
        admin = {
            'id': 'U-ADMIN',
            'name': 'Admin',
            'role': 'admin',
            'salt': salt,
            'hash': hash_pin(pin, salt),
        }
        data['users'].append(admin)
        data['leads'].extend(_sample_leads(admin['name']))
        _write(data)
        os.makedirs(DATA, exist_ok=True)
        with open(PIN_PATH, 'w', encoding='utf-8') as handle:
            handle.write('Admin %s\n' % pin)
        try:
            os.chmod(PIN_PATH, 0o600)
        except OSError:
            pass


def _log(data, actor, event, details):
    data['activity'].append({
        'time': now_stamp(),
        'actor': actor,
        'event': event,
        'details': details,
    })
    data['activity'] = data['activity'][-80:]


def public_user(user):
    return {'id': user['id'], 'name': user['name'], 'role': user['role']}


def _sheet():
    if not os.path.exists(os.path.join(DATA, 'sheet.json')):
        return None
    import sheet_db
    return sheet_db.connect()


def using_sheet():
    return os.path.exists(os.path.join(DATA, 'sheet.json'))


def prepare():
    database = _sheet()
    if database:
        return database.ping()
    ensure_seed()
    return None


def authenticate(name, pin):
    database = _sheet()
    if database:
        return database.authenticate(name, pin)
    ensure_seed()
    with _lock:
        data = _read()
    found = next((user for user in data['users'] if norm(user['name']) == norm(name)), None)
    if not found or hash_pin(pin, found['salt']) != found['hash']:
        raise ValueError('Invalid name or PIN')
    return public_user(found)


def _user_by_name(data, name):
    return next((user for user in data['users'] if user['name'] == name), None)


def can_see(user, lead):
    if user['role'] in ('admin', 'manager'):
        return True
    if user['role'] == 'sales':
        owner = lead.get('assignee') or ''
        if not norm(owner):
            return True
        return names_match(owner, user['name'])
    caller = lead.get('telecaller') or ''
    if not norm(caller):
        return False
    return names_match(caller, user['name'])


def lead_public(lead):
    shown = dict(lead)
    shown.pop('sample', None)
    shown['sample'] = bool(lead.get('sample'))
    return shown


def dashboard(user):
    database = _sheet()
    if database:
        return database.dashboard(user)
    ensure_seed()
    with _lock:
        data = _read()
    leads = [lead_public(lead) for lead in data['leads'] if can_see(user, lead)]
    staff = [public_user(person) for person in data['users']]
    return {
        'today': today_key(),
        'user': user,
        'staff': staff,
        'statuses': STATUSES,
        'actions': ACTIONS,
        'documents': DOCS,
        'leads': leads,
    }


def _new_id(data, prefix):
    used = {item['id'] for item in data['leads']}
    while True:
        item_id = prefix + secrets.token_hex(4).upper()
        if item_id not in used:
            return item_id


def create_lead(user, fields):
    database = _sheet()
    if database:
        return database.create_lead(user, fields)
    name = str(fields.get('customer_name') or '').strip()
    phone = str(fields.get('phone') or '').strip()
    if not name:
        raise ValueError('Customer name is required')
    if len(phone_key(phone)) < 10:
        raise ValueError('Enter a phone number with at least 10 digits')
    maps = str(fields.get('maps_url') or '').strip()
    if maps and not (maps.startswith('https://') or maps.startswith('http://')):
        raise ValueError('Map link must start with http:// or https://')
    with _lock:
        data = _read()
        key = phone_key(phone)
        existing = next((lead for lead in data['leads'] if phone_key(lead.get('phone')) == key), None)
        if existing:
            for field in ('address', 'maps_url', 'site_kw', 'brand', 'quoted_price', 'visit_at', 'telecaller', 'assignee'):
                incoming = str(fields.get(field) or '').strip()
                if incoming and not str(existing.get(field) or '').strip():
                    existing[field] = incoming
            remark = str(fields.get('remarks') or '').strip()
            if remark:
                previous = str(existing.get('remarks') or '').strip()
                extra = '[Also submitted %s] %s' % (now_stamp(), remark)
                existing['remarks'] = (previous + '\n' + extra).strip() if previous else extra
            existing['updated_by'] = user['name']
            existing['updated_at'] = now_stamp()
            _log(data, user['name'], 'MERGE', {'lead': existing['id'], 'phone_key': key})
            _write(data)
            return {'lead': lead_public(existing), 'merged': True}

        assignee = str(fields.get('assignee') or '').strip()
        if assignee:
            match = [person for person in data['users'] if names_match(assignee, person['name'])]
            if len(match) != 1:
                raise ValueError('Unknown employee')
            assignee = match[0]['name']
        if user['role'] == 'sales' and assignee and not names_match(assignee, user['name']):
            raise ValueError('You can only assign a visit to yourself')
        if user['role'] == 'sales' and assignee:
            assignee = user['name']
        lead = {
            'id': _new_id(data, 'EL-'),
            'sample': False,
            'created_at': now_stamp(),
            'customer_name': name,
            'phone': phone,
            'address': str(fields.get('address') or '').strip(),
            'maps_url': maps,
            'site_kw': str(fields.get('site_kw') or '').strip(),
            'brand': str(fields.get('brand') or '').strip(),
            'quoted_price': str(fields.get('quoted_price') or '').strip(),
            'visit_at': str(fields.get('visit_at') or '').strip(),
            'remarks': str(fields.get('remarks') or '').strip(),
            'telecaller': user['name'] if user['role'] == 'telecaller' else str(fields.get('telecaller') or '').strip(),
            'assignee': assignee,
            'status': '',
            'visit_remarks': '',
            'next_action': '',
            'next_action_date': '',
            'next_action_assignee': '',
            'documents': [],
            'updated_by': user['name'],
            'updated_at': now_stamp(),
        }
        data['leads'].append(lead)
        _log(data, user['name'], 'CREATE_LEAD', {'lead': lead['id'], 'name': name})
        _write(data)
        return {'lead': lead_public(lead), 'merged': False}


def update_lead(user, lead_id, changes):
    database = _sheet()
    if database:
        return database.update_lead(user, lead_id, changes)
    changes = changes or {}
    with _lock:
        data = _read()
        lead = next((item for item in data['leads'] if item['id'] == lead_id), None)
        if not lead:
            raise ValueError('Lead not found')
        if not can_see(user, lead):
            raise ValueError('Access denied')
        allowed = list(FOLLOW_FIELDS)
        if user['role'] in ('telecaller', 'sales', 'admin', 'manager'):
            allowed.extend(ASSIGN_FIELDS)
        if user['role'] != 'telecaller':
            allowed.extend(OUTCOME_FIELDS)
        for key, raw in changes.items():
            if key not in allowed:
                raise ValueError('Field not allowed: %s' % key)
            if key == 'documents':
                picked = raw if isinstance(raw, list) else str(raw or '').split(',')
                keys = [item.strip() for item in picked if str(item).strip()]
                known = [item[0] for item in DOCS]
                if any(item not in known for item in keys):
                    raise ValueError('Invalid document')
                lead['documents'] = keys
                continue
            value = str(raw or '').strip()[:1500]
            if key == 'status' and value and value not in STATUSES:
                raise ValueError('Invalid status')
            if key == 'next_action' and value and value not in ACTIONS:
                raise ValueError('Invalid action')
            if key == 'next_action_date' and value and len(value) != 10:
                raise ValueError('Invalid date')
            if key in ('assignee', 'next_action_assignee') and value:
                match = [person for person in data['users'] if names_match(value, person['name'])]
                if len(match) != 1:
                    raise ValueError('Unknown employee')
                value = match[0]['name']
            if key == 'assignee' and user['role'] == 'sales' and value and not names_match(value, user['name']):
                raise ValueError('You can only assign a visit to yourself')
            if key == 'assignee' and user['role'] == 'sales' and value:
                value = user['name']
            lead[key] = value
        lead['updated_by'] = user['name']
        lead['updated_at'] = now_stamp()
        _log(data, user['name'], 'UPDATE', {'lead': lead_id, 'name': lead['customer_name'], 'fields': sorted(changes.keys())})
        _write(data)
        return lead_public(lead)


def list_users(user):
    database = _sheet()
    if database:
        return database.list_users(user)
    if user['role'] != 'admin':
        raise ValueError('Only an admin can do that')
    with _lock:
        data = _read()
    return [public_user(person) for person in data['users']]


def create_user(actor, name, role, pin):
    database = _sheet()
    if database:
        return database.create_user(actor, name, role, pin)
    if actor['role'] != 'admin':
        raise ValueError('Only an admin can do that')
    name = str(name or '').strip()
    role = str(role or '').strip()
    if not name:
        raise ValueError('Name is required')
    if role not in ROLES:
        raise ValueError('Invalid role')
    check_pin_rules(pin)
    with _lock:
        data = _read()
        if any(norm(person['name']) == norm(name) for person in data['users']):
            raise ValueError('That name is already used')
        salt = secrets.token_hex(16)
        person = {
            'id': 'U-' + secrets.token_hex(4).upper(),
            'name': name,
            'role': role,
            'salt': salt,
            'hash': hash_pin(pin, salt),
        }
        data['users'].append(person)
        _log(data, actor['name'], 'CREATE_USER', {'name': name, 'role': role})
        _write(data)
        return public_user(person)


def delete_user(actor, user_id):
    database = _sheet()
    if database:
        return database.delete_user(actor, user_id)
    if actor['role'] != 'admin':
        raise ValueError('Only an admin can do that')
    with _lock:
        data = _read()
        person = next((item for item in data['users'] if item['id'] == user_id), None)
        if not person:
            raise ValueError('Employee not found')
        if person['id'] == actor['id']:
            raise ValueError('You cannot delete your own sign-in')
        admins = [item for item in data['users'] if item['role'] == 'admin']
        if person['role'] == 'admin' and len(admins) <= 1:
            raise ValueError('Keep at least one admin')
        data['users'] = [item for item in data['users'] if item['id'] != user_id]
        _log(data, actor['name'], 'DELETE_USER', {'name': person['name'], 'role': person['role']})
        _write(data)
        return True


def activity_for(user):
    database = _sheet()
    if database:
        return database.activity_for(user)
    if user['role'] != 'admin':
        raise ValueError('Only an admin can do that')
    with _lock:
        data = _read()
    return list(reversed(data['activity'][-40:]))

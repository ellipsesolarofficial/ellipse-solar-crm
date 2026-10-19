const $ = (id) => document.getElementById(id);
const page = document.body.dataset.page;

const call = async (url, options = {}) => {
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

const phoneDigits = (value) => {
  const digits = String(value || '').replace(/\D/g, '');
  if (digits.length < 10) return '';
  return digits.length === 10 ? '91' + digits : digits;
};

const priceNumber = (value) => {
  const text = String(value || '').trim().toLowerCase().replace(/₹/g, '').replace(/,/g, '');
  const amount = parseFloat(text);
  if (!amount) return 0;
  if (text.includes('crore')) return amount * 10000000;
  if (text.includes('lakh')) return amount * 100000;
  return amount;
};

const inr = (value) => new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 0,
}).format(value);

const emi = (principal) => {
  if (principal < 1000) return 0;
  const rate = 0.10 / 12;
  const months = 60;
  const factor = (1 + rate) ** months;
  return principal * rate * factor / (factor - 1);
};

const nav = (user) => {
  const slot = $('nav');
  if (!slot || !user) return;
  const admin = user.role === 'admin' ? '<a href="/admin">Admin</a>' : '';
  slot.innerHTML = admin + '<button type="button" id="logout">Log out</button>';
  $('logout').onclick = async () => {
    await call('/api/logout', { method: 'POST', body: '{}' });
    location.href = '/login';
  };
};

const staffOptions = (staff, selected, empty) =>
  '<option value="">' + escapeHtml(empty || 'Select') + '</option>' +
  staff.map((person) => '<option value="' + escapeHtml(person.name) + '"' +
    (person.name === selected ? ' selected' : '') + '>' + escapeHtml(person.name) + '</option>').join('');

if (page === 'login') {
  $('loginForm').onsubmit = async (event) => {
    event.preventDefault();
    $('error').textContent = '';
    const form = new FormData(event.target);
    try {
      await call('/api/login', {
        method: 'POST',
        body: JSON.stringify({ name: form.get('name'), pin: form.get('pin') }),
      });
      location.href = '/';
    } catch (error) {
      $('error').textContent = error.message;
    }
  };
}

if (page === 'leads' || page === 'admin') {
  call('/api/session').then((data) => {
    if (page === 'admin' && data.user.role !== 'admin') {
      location.href = '/';
      return;
    }
    nav(data.user);
    if (page === 'leads') startLeads(data.user);
    else startAdmin(data.user);
  }).catch(() => { location.href = '/login'; });
}

function startLeads(user) {
  let pack = null;
  let statusFilter = 'ALL';
  let dayFilter = '';
  let editing = null;

  const splitVisit = (value) => {
    const text = String(value || '').trim().replace(' ', 'T');
    return {
      date: /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : '',
      time: text.length >= 16 && text[10] === 'T' ? text.slice(11, 16) : '',
    };
  };

  const joinVisit = (date, time) => {
    const day = String(date || '').trim();
    const clock = String(time || '').trim();
    return day && clock ? day + 'T' + clock : day;
  };

  document.querySelectorAll('input[type="date"], input[type="time"]').forEach((input) => {
    input.addEventListener('click', () => {
      if (typeof input.showPicker === 'function') {
        try { input.showPicker(); } catch (error) {}
      }
    });
  });

  const load = async () => {
    pack = await call('/api/leads');
    if (pack.source) {
      $('sample').hidden = false;
      $('sample').textContent = pack.source;
    } else {
      $('sample').hidden = !pack.leads.some((lead) => lead.sample);
    }
    render();
  };

  const dueState = (lead) => {
    const day = String(lead.next_action_date || '').slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !lead.next_action) return '';
    if (lead.next_action === 'Lost' || lead.next_action === 'Ready To Process') return '';
    if (day < pack.today) return 'overdue';
    if (day === pack.today) return 'today';
    return '';
  };

  const rows = () => {
    const query = $('search').value.trim().toLowerCase();
    const due = $('due').value;
    return pack.leads.filter((lead) => {
      if (statusFilter !== 'ALL' && (lead.status || '') !== statusFilter) return false;
      if (dayFilter && String(lead.visit_at || '').slice(0, 10) !== dayFilter) return false;
      const state = dueState(lead);
      if (due === 'today' && state !== 'today') return false;
      if (due === 'overdue' && state !== 'overdue') return false;
      if (due === 'undated' && lead.visit_at) return false;
      if (!query) return true;
      const hay = [lead.customer_name, lead.phone, lead.address, lead.brand].join(' ').toLowerCase();
      return hay.includes(query);
    }).sort((a, b) => {
      const rank = (lead) => (dueState(lead) === 'overdue' ? 0 : 1);
      return rank(a) - rank(b) || String(a.visit_at || '9999').localeCompare(String(b.visit_at || '9999'));
    });
  };

  const renderDays = () => {
    const start = new Date(pack.today + 'T00:00:00');
    const localKey = (date) => date.getFullYear() + '-' +
      String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    const days = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const date = new Date(start);
      date.setDate(start.getDate() + offset);
      const key = localKey(date);
      const count = pack.leads.filter((lead) => String(lead.visit_at || '').slice(0, 10) === key).length;
      days.push({ key, label: date.toLocaleDateString('en-IN', { weekday: 'short' }), date: date.getDate(), count });
    }
    $('days').innerHTML = '<button type="button" class="day' + (dayFilter ? '' : ' on') + '" data-day=""><span>All</span><em>visits</em></button>' +
      days.map((day) => '<button type="button" class="day' + (dayFilter === day.key ? ' on' : '') + '" data-day="' + day.key + '"><span>' +
        day.label + '</span><strong>' + day.date + '</strong><em>' + day.count + '</em></button>').join('');
    $('days').querySelectorAll('.day').forEach((button) => {
      button.onclick = () => { dayFilter = button.dataset.day; render(); };
    });
  };

  const renderChips = () => {
    const counts = { ALL: pack.leads.length };
    pack.statuses.forEach((status) => { counts[status] = 0; });
    let blank = 0;
    pack.leads.forEach((lead) => {
      if (!lead.status) blank += 1;
      else if (counts[lead.status] !== undefined) counts[lead.status] += 1;
    });
    const chips = [{ id: 'ALL', label: 'All ' + counts.ALL }, { id: '', label: 'Not updated ' + blank }]
      .concat(pack.statuses.map((status) => ({ id: status, label: status + ' ' + counts[status] })));
    $('chips').innerHTML = chips.map((chip) =>
      '<button type="button" class="chip' + (statusFilter === chip.id ? ' on' : '') + '" data-status="' + escapeHtml(chip.id) + '">' +
      escapeHtml(chip.label) + '</button>').join('');
    $('chips').querySelectorAll('.chip').forEach((button) => {
      button.onclick = () => { statusFilter = button.dataset.status; render(); };
    });
  };

  const renderList = () => {
    const leads = rows();
    if (!leads.length) {
      $('list').innerHTML = '<p class="empty">No leads match.</p>';
      return;
    }
    $('list').innerHTML = leads.map((lead) => {
      const phone = phoneDigits(lead.phone);
      const amount = priceNumber(lead.quoted_price);
      const monthly = emi(amount);
      const visitDay = String(lead.visit_at || '').slice(0, 10);
      const state = dueState(lead);
      const docs = (lead.documents || []).length;
      const bits = [
        lead.site_kw ? escapeHtml(lead.site_kw) + ' kW' : '',
        escapeHtml(lead.brand || ''),
        amount ? escapeHtml(inr(amount)) : '',
        monthly ? 'EMI ' + escapeHtml(inr(monthly)) + '/mo' : '',
        docs ? docs + '/' + pack.documents.length + ' docs' : '',
      ].filter(Boolean).join(' · ');
      const next = lead.next_action
        ? '<p class="next ' + (state === 'overdue' ? 'overdue' : '') + '">' + escapeHtml(lead.next_action) +
          (lead.next_action_date ? ' · ' + escapeHtml(lead.next_action_date) : '') +
          (state === 'overdue' ? ' · Overdue' : '') + '</p>'
        : '';
      return '<article class="lead' + (visitDay === pack.today ? ' today' : '') + '">' +
        '<div class="lead-top"><div><h2>' + escapeHtml(lead.customer_name) + '</h2>' +
        '<p class="meta">' + escapeHtml(lead.phone || '') + (lead.address ? ' · ' + escapeHtml(lead.address) : '') + '</p></div>' +
        '<div class="status">' + (visitDay === pack.today ? '<div class="today-word">Today</div>' : '') +
        escapeHtml(lead.status || 'Not updated') + '</div></div>' +
        (bits ? '<p class="facts">' + bits + '</p>' : '') + next +
        '<div class="row-actions">' +
        (phone ? '<a href="tel:+' + phone + '">Call</a><a href="https://wa.me/' + phone + '" target="_blank" rel="noopener">WhatsApp</a>' : '') +
        (lead.maps_url ? '<a href="' + escapeHtml(lead.maps_url) + '" target="_blank" rel="noopener">Map</a>' : '') +
        '<button type="button" class="text-btn" data-edit="' + escapeHtml(lead.id) + '">Update</button></div></article>';
    }).join('');
    $('list').querySelectorAll('[data-edit]').forEach((button) => {
      button.onclick = () => openEdit(button.dataset.edit);
    });
  };

  const render = () => {
    renderDays();
    renderChips();
    renderList();
  };

  const fillPeople = (select, selected) => {
    const people = user.role === 'sales' ? pack.staff.filter((person) => person.name === user.name) : pack.staff;
    select.innerHTML = staffOptions(people, selected, 'Unassigned');
  };

  $('search').oninput = render;
  $('due').onchange = render;

  const addButton = document.createElement('button');
  addButton.type = 'button';
  addButton.textContent = 'Add lead';
  $('nav').prepend(addButton);
  addButton.onclick = () => {
    $('addError').textContent = '';
    fillPeople($('addAssignee'), user.role === 'sales' ? user.name : '');
    $('addDialog').showModal();
  };
  $('addCancel').onclick = () => $('addDialog').close();
  $('addForm').onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = Object.fromEntries(form.entries());
    payload.visit_at = joinVisit(payload.visit_date, payload.visit_time);
    delete payload.visit_date;
    delete payload.visit_time;
    try {
      const result = await call('/api/leads', { method: 'POST', body: JSON.stringify(payload) });
      $('addForm').reset();
      $('addDialog').close();
      await load();
      if (result.merged) {
        $('sample').hidden = false;
        $('sample').textContent = 'That phone was already on a lead. The new details were added there.';
      }
    } catch (error) {
      $('addError').textContent = error.message;
    }
  };

  const openEdit = (id) => {
    editing = pack.leads.find((lead) => lead.id === id);
    if (!editing) return;
    const form = $('editForm');
    $('editTitle').textContent = editing.customer_name;
    $('editStatus').innerHTML = '<option value="">Not updated</option>' +
      pack.statuses.map((status) => '<option' + (status === editing.status ? ' selected' : '') + '>' + escapeHtml(status) + '</option>').join('');
    $('editAction').innerHTML = '<option value="">None</option>' +
      pack.actions.map((action) => '<option' + (action === editing.next_action ? ' selected' : '') + '>' + escapeHtml(action) + '</option>').join('');
    form.elements.next_action_date.value = editing.next_action_date || '';
    const visit = splitVisit(editing.visit_at);
    form.elements.visit_date.value = visit.date;
    form.elements.visit_time.value = visit.time;
    form.elements.visit_remarks.value = editing.visit_remarks || '';
    fillPeople($('editAssignee'), editing.assignee || '');
    fillPeople($('editNextAssignee'), editing.next_action_assignee || '');
    const outcome = user.role !== 'telecaller';
    $('statusField').hidden = !outcome;
    const showDocs = () => {
      $('docsField').hidden = !outcome || $('editStatus').value !== 'Converted (Docs. Received)';
    };
    $('docs').innerHTML = pack.documents.map(([key, label]) =>
      '<label><input type="checkbox" value="' + key + '"' + ((editing.documents || []).includes(key) ? ' checked' : '') + '> ' +
      escapeHtml(label) + '</label>').join('');
    $('editStatus').onchange = showDocs;
    showDocs();
    $('editError').textContent = '';
    $('editDialog').showModal();
  };

  $('editCancel').onclick = () => $('editDialog').close();
  $('editForm').onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const changes = {
      next_action: form.get('next_action') || '',
      next_action_date: form.get('next_action_date') || '',
      next_action_assignee: form.get('next_action_assignee') || '',
      assignee: form.get('assignee') || '',
      visit_at: joinVisit(form.get('visit_date'), form.get('visit_time')),
      visit_remarks: form.get('visit_remarks') || '',
    };
    if (user.role !== 'telecaller') {
      changes.status = form.get('status') || '';
      changes.documents = [...$('docs').querySelectorAll('input:checked')].map((box) => box.value);
    }
    try {
      await call('/api/leads/' + editing.id, { method: 'PATCH', body: JSON.stringify(changes) });
      $('editDialog').close();
      await load();
    } catch (error) {
      $('editError').textContent = error.message;
    }
  };

  load().catch((error) => { $('list').innerHTML = '<p class="error">' + escapeHtml(error.message) + '</p>'; });
}

function startAdmin(user) {
  let pendingDelete = '';

  const load = async () => {
    const data = await call('/api/admin');
    $('people').innerHTML = data.users.map((person) =>
      '<li class="person"><div><strong>' + escapeHtml(person.name) + '</strong><div class="meta">' +
      escapeHtml({ admin: 'Admin', manager: 'Manager', sales: 'Sales', telecaller: 'Telecaller' }[person.role] || person.role) + '</div></div>' +
      (person.id === user.id ? '<span class="meta">You</span>' :
        '<button type="button" class="quiet" data-id="' + escapeHtml(person.id) + '">' +
        (pendingDelete === person.id ? 'Confirm delete' : 'Delete') + '</button>') + '</li>').join('');
    $('people').querySelectorAll('button').forEach((button) => {
      button.onclick = () => remove(button.dataset.id);
    });
    const line = (item) => {
      const details = item.details || {};
      if (item.event === 'CREATE_USER') return item.actor + ' added ' + details.name + ' as ' + details.role;
      if (item.event === 'DELETE_USER') return item.actor + ' removed ' + details.name;
      if (item.event === 'CREATE_LEAD') return item.actor + ' added ' + details.name;
      if (item.event === 'MERGE') return item.actor + ' merged a repeat enquiry into ' + details.lead;
      if (item.event === 'UPDATE') return item.actor + ' updated ' + (details.name || details.lead);
      return item.actor + ' · ' + item.event;
    };
    $('activity').innerHTML = data.activity.length ? data.activity.map((item) =>
      '<li><span>' + escapeHtml(line(item)) + '</span><time>' + escapeHtml(item.time) + '</time></li>').join('') :
      '<li>No activity yet.</li>';
  };

  const remove = async (id) => {
    if (pendingDelete !== id) {
      pendingDelete = id;
      await load();
      return;
    }
    pendingDelete = '';
    try {
      await call('/api/users/' + encodeURIComponent(id), { method: 'DELETE' });
      $('userError').textContent = '';
      await load();
    } catch (error) {
      $('userError').textContent = error.message;
    }
  };

  $('userForm').onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      await call('/api/users', {
        method: 'POST',
        body: JSON.stringify({ name: form.get('name'), role: form.get('role'), pin: form.get('pin') }),
      });
      event.target.reset();
      $('userError').textContent = '';
      await load();
    } catch (error) {
      $('userError').textContent = error.message;
    }
  };

  load().catch((error) => { $('userError').textContent = error.message; });
}

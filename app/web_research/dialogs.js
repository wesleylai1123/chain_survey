import { previewMappings, previewValue } from './model.js';
import { byId, element, icon, icons, request, setOptions, status, textButton } from './ui.js';

const groupKey = 'chain-survey.research.groups.v1';

export function setupDialogs({ getSettings, restoreGroup, notify, onImport }) {
  setupImport(onImport, notify);
  setupGroups(getSettings, restoreGroup, notify);
}

function setupImport(onImport, notify) {
  const dialog = byId('import-dialog');
  const form = byId('import-form');
  const mapping = byId('import-mapping');
  const fileInput = byId('import-file');
  const fileLabel = byId('import-file-label');
  const target = byId('file-drop');
  const date = byId('import-date');
  const available = byId('import-available');
  const frequency = byId('import-frequency');
  const columns = byId('import-columns');
  const preview = byId('import-preview');
  const message = byId('import-status');
  const submit = byId('submit-import');
  let current;
  let controller;
  let writing = false;
  let checks = [];

  function reset() {
    controller?.abort();
    current = null;
    checks = [];
    form.reset();
    columns.replaceChildren();
    preview.querySelectorAll('thead, tbody').forEach(node => node.remove());
    fileLabel.textContent = '選擇或拖入 CSV 檔案';
    mapping.disabled = true;
    mapping.hidden = true;
    submit.disabled = true;
    status(message, '');
  }

  function selectedColumns() {
    return checks.filter(input => input.checked && !input.disabled).map(input => input.value);
  }

  function updateChoices() {
    if (date.value === available.value) available.value = '';
    for (const option of available.options) option.disabled = option.value === date.value;
    for (const input of checks) {
      input.disabled = input.value === date.value || input.value === available.value;
      input.parentElement.hidden = input.disabled;
    }
    const count = selectedColumns().length;
    submit.disabled = writing || !current || !count || count > 100;
    if (count > 100) status(message, '最多可匯入 100 個數值欄。', true);
    else if (current && !writing) status(message, '');
  }

  function renderPreview(headers, rows) {
    const head = element('thead');
    const header = element('tr');
    for (const name of headers) {
      const th = element('th', name);
      th.scope = 'col';
      header.append(th);
    }
    head.append(header);
    const body = element('tbody');
    for (const row of rows) {
      const tr = element('tr');
      tr.append(...headers.map((name, index) => element('td', previewValue(row, name, index) ?? '')));
      body.append(tr);
    }
    preview.querySelectorAll('thead, tbody').forEach(node => node.remove());
    preview.append(head, body);
  }

  async function showPreview(file) {
    if (!file || writing) return;
    controller?.abort();
    controller = new AbortController();
    const { signal } = controller;
    current = null;
    mapping.hidden = true;
    mapping.disabled = true;
    submit.disabled = true;
    fileLabel.textContent = file.name;
    if (file.size > 12 * 1024 * 1024) return status(message, 'CSV 已超過本機服務的 12 MB 請求上限。', true);
    status(message, '正在預覽 CSV…');
    try {
      const text = await file.text();
      if (signal.aborted) return;
      const { headers, rows } = await request('/api/csv/preview', { body: { text }, signal });
      if (signal.aborted) return;
      if (headers.length < 2 || !rows.length) throw new Error('CSV 至少需要一列資料、日期欄和一個數值欄。');
      current = { file, text };
      const guess = previewMappings(headers, rows);
      const entries = headers.map(name => [name, name]);
      setOptions(date, entries);
      setOptions(available, [['', '未提供'], ...entries]);
      date.value = guess.date;
      available.value = guess.available;
      checks = headers.map(name => {
        const input = element('input');
        input.type = 'checkbox';
        input.value = name;
        input.checked = guess.columns.includes(name);
        return input;
      });
      columns.replaceChildren(...checks.map(input => {
        const label = element('label');
        label.append(input, element('span', input.value));
        return label;
      }));
      renderPreview(headers, rows);
      mapping.hidden = false;
      mapping.disabled = false;
      updateChoices();
    } catch (error) {
      if (!signal.aborted) status(message, error.message, true);
    }
  }

  byId('open-import').addEventListener('click', () => {
    reset();
    dialog.showModal();
    fileInput.focus();
  });
  for (const close of dialog.querySelectorAll('[data-close-dialog]')) close.addEventListener('click', () => {
    if (!writing) dialog.close();
  });
  dialog.addEventListener('cancel', event => { if (writing) event.preventDefault(); });
  dialog.addEventListener('close', reset);
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    void showPreview(file);
  });
  target.addEventListener('dragover', event => {
    event.preventDefault();
    if (!writing) target.classList.add('is-dragging');
  });
  target.addEventListener('dragleave', event => {
    if (!target.contains(event.relatedTarget)) target.classList.remove('is-dragging');
  });
  target.addEventListener('drop', event => {
    event.preventDefault();
    target.classList.remove('is-dragging');
    void showPreview(event.dataTransfer.files[0]);
  });
  for (const control of [date, available, columns]) control.addEventListener('change', updateChoices);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const values = selectedColumns();
    if (!current || writing || !values.length || values.length > 100) return;
    const body = {
      text: current.text,
      filename: current.file.name,
      date_column: date.value,
      columns: values,
      available_column: available.value || null,
      source: byId('import-source').value.trim(),
      unit: byId('import-unit').value.trim(),
      frequency: frequency.value,
    };
    writing = true;
    const closeButtons = [...dialog.querySelectorAll('[data-close-dialog]')];
    for (const node of [...closeButtons, mapping, fileInput, submit]) node.disabled = true;
    status(message, '正在匯入序列…');
    try {
      const { series } = await request('/api/csv/import', { body });
      writing = false;
      dialog.close();
      notify('已匯入 ' + series.length + ' 條序列。');
      onImport(series);
    } catch (error) {
      status(message, error.message, true);
    } finally {
      writing = false;
      for (const node of [...closeButtons, fileInput]) node.disabled = false;
      mapping.disabled = !current;
      submit.disabled = !current || !values.length;
    }
  });
}

function readGroups() {
  const data = JSON.parse(localStorage.getItem(groupKey) ?? '[]');
  if (!Array.isArray(data)) throw new Error('群組儲存格式無法讀取。');
  return data.filter(item => item && typeof item.name === 'string' && item.settings);
}

function saveGroups(groups) {
  localStorage.setItem(groupKey, JSON.stringify(groups));
}

function setupGroups(getSettings, restoreGroup, notify) {
  const dialog = byId('groups-dialog');
  const form = byId('group-form');
  const nameInput = byId('group-name');
  const list = byId('group-list');
  const message = byId('group-status');
  let confirming = '';

  function displayGroups() {
    let groups;
    try {
      groups = readGroups();
    } catch {
      status(message, '無法讀取本機研究群組。', true);
      list.replaceChildren();
      return null;
    }
    let confirmFocus;
    const nodes = groups.map(group => {
      const li = element('li', undefined, 'group-row');
      const title = element('span', group.name);
      const actions = element('div', undefined, 'group-actions');
      if (confirming === group.name) {
        li.classList.add('group-confirm');
        title.textContent = '刪除「' + group.name + '」？';
        const cancel = textButton('保留');
        const remove = textButton('確認刪除', 'button button-danger');
        confirmFocus = cancel;
        cancel.addEventListener('click', () => {
          confirming = '';
          displayGroups();
          nameInput.focus();
        });
        remove.addEventListener('click', () => {
          try {
            saveGroups(readGroups().filter(item => item.name !== group.name));
            confirming = '';
            status(message, '已刪除「' + group.name + '」。');
            displayGroups();
            nameInput.focus();
          } catch {
            status(message, '無法刪除本機群組。', true);
          }
        });
        actions.append(cancel, remove);
      } else {
        const load = textButton('套用');
        load.setAttribute('aria-label', '套用群組 ' + group.name);
        load.addEventListener('click', () => {
          try {
            const missing = restoreGroup(group.settings);
            dialog.close();
            notify('已套用「' + group.name + '」' + (missing > 0 ? '，' + missing + ' 條原序列目前不在資料庫。' : '。'));
          } catch (error) {
            status(message, error.message, true);
          }
        });
        const remove = textButton('刪除', 'button button-quiet');
        remove.setAttribute('aria-label', '刪除群組 ' + group.name);
        remove.prepend(icon('trash-2'));
        remove.addEventListener('click', () => {
          confirming = group.name;
          status(message, '');
          displayGroups();
        });
        actions.append(load, remove);
      }
      li.append(title, actions);
      return li;
    });
    list.replaceChildren(...(nodes.length ? nodes : [element('li', '尚未儲存研究群組。', 'group-empty')]));
    icons();
    confirmFocus?.focus();
    return groups;
  }

  function open(focusName) {
    form.reset();
    confirming = '';
    status(message, '');
    displayGroups();
    dialog.showModal();
    if (focusName) nameInput.focus();
  }
  byId('open-groups').addEventListener('click', () => open(false));
  byId('save-group').addEventListener('click', () => open(true));
  for (const close of dialog.querySelectorAll('[data-close-dialog]')) close.addEventListener('click', () => dialog.close());

  form.addEventListener('submit', event => {
    event.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return status(message, '請輸入群組名稱。', true);
    try {
      const groups = readGroups();
      if (groups.some(item => item.name === name)) return status(message, '此名稱已存在，請輸入不同名稱。', true);
      saveGroups([...groups, { name, settings: getSettings() }]);
      form.reset();
      confirming = '';
      status(message, '已儲存「' + name + '」。');
      displayGroups();
      nameInput.focus();
    } catch {
      status(message, '無法儲存本機群組。', true);
    }
  });

  addEventListener('storage', event => {
    if (dialog.open && event.key === groupKey) displayGroups();
  });
}

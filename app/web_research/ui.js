export const byId = id => document.getElementById(id);

export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function icon(name, className) {
  const node = element('i', undefined, className);
  node.dataset.lucide = name;
  node.setAttribute('aria-hidden', 'true');
  return node;
}

export function icons() {
  globalThis.lucide?.createIcons?.();
}

export function setOptions(select, entries) {
  select.replaceChildren(...entries.map(([value, label]) => new Option(label, value)));
}

export function textButton(text, className = 'button') {
  const node = element('button', text, className);
  node.type = 'button';
  return node;
}

export function status(node, message, error = false) {
  node.textContent = message;
  node.classList.toggle('is-error', error);
  node.hidden = !message;
}

export async function request(path, { body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  const options = { headers, signal, credentials: 'same-origin' };
  if (body !== undefined) {
    options.method = 'POST';
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('無法連線到本機研究服務。');
  }
  const data = await response.json().catch(() => null);
  if (data?.error) throw new Error(data.error);
  if (!response.ok || !data) throw new Error(`本機服務回應異常（${response.status}）。`);
  return data;
}

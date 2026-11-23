/* 無人機練習紀錄 — Service Worker
 * 讓網站可以「安裝成 App」，並在沒網路時顯示上次讀到的成績。
 * 修改網頁後，把 VERSION 改一個數字，App 就會更新。 */
const VERSION = 'v2';
const CACHE = 'drone-practice-' + VERSION;
const SHELL = ['./', './index.html', './manifest.json', './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('drone-practice-') && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// 先試網路，成功就順便存一份；沒網路時拿存的那份
async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, {ignoreSearch: req.mode === 'navigate'});
    if (hit) return hit;
    if (req.mode === 'navigate') return cache.match('./index.html');
    throw err;
  }
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // 儲存、刪除等一律直接連線
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.includes('/api/')) {
    if (url.pathname.endsWith('/api/ping')) {
      e.respondWith(fetch(req).catch(() => new Response(JSON.stringify({offline: true}),
        {status: 503, headers: {'Content-Type': 'application/json'}})));
      return;
    }
    if (url.pathname.endsWith('.csv')) return;      // 匯出不快取
    e.respondWith(networkFirst(req));               // 學生、紀錄：離線時顯示上次的資料
    return;
  }
  // 網頁本身、圖示、圖表元件、字型
  e.respondWith(networkFirst(req));
});

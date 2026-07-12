/**
 * MMD Viewer Service Worker
 *
 * 策略说明：
 * - models/, vmd/, audio/, libs/ → Cache First（优先从缓存读取，首次访问时缓存）
 * - index.html → Network First（优先取最新 HTML，离线时回退缓存）
 * - CDN (unpkg/jsdelivr) → Network Only（库文件变动频繁，不缓存）
 */

const CACHE_NAME = 'mmd-viewer-cache-v3';

// 需要缓存优先的路径前缀
const CACHE_FIRST_PREFIXES = [
  '/models/',
  '/vmd/',
  '/audio/',
  '/libs/',
];

// 需要网络优先的路径
const NETWORK_FIRST_PATHS = [
  '/index.html',
  '/',
];

function shouldCacheFirst(url) {
  const pathname = new URL(url).pathname;
  return CACHE_FIRST_PREFIXES.some(prefix => pathname.startsWith(prefix));
}

function shouldNetworkFirst(url) {
  const pathname = new URL(url).pathname;
  return NETWORK_FIRST_PATHS.some(path => pathname === path);
}

function isCDN(url) {
  try {
    const hostname = new URL(url).hostname;
    return hostname.includes('unpkg.com') || hostname.includes('jsdelivr.net') || hostname.includes('cdn.jsdelivr.net');
  } catch {
    return false;
  }
}

// ===== 安装：清理旧缓存 =====
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  // 立即激活，不等待所有页面关闭
  self.skipWaiting();
});

// ===== 激活：清理旧版本缓存 =====
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => {
            console.log('[SW] Removing old cache:', key);
            return caches.delete(key);
          })
      );
    }).then(() => {
      // 立即控制所有页面，不需刷新
      return self.clients.claim();
    })
  );
});

// ===== 请求拦截 =====
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 只处理 GET 请求
  if (request.method !== 'GET') return;

  // CDN 请求不缓存（始终用最新版本）
  if (isCDN(request.url)) return;

  // 缓存优先策略（模型/舞蹈/音频/库文件）
  if (shouldCacheFirst(request.url)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // 网络优先策略（index.html）
  if (shouldNetworkFirst(request.url)) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 其他请求不拦截
});

/**
 * Cache First 策略：
 * 1. 先查缓存，命中则直接返回
 * 2. 未命中则从网络获取，缓存后返回
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    console.log('[SW] Cache HIT:', request.url);
    return cached;
  }

  console.log('[SW] Cache MISS, fetching:', request.url);
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      // 对模型/音频等大文件使用流式克隆以避免内存压力
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.error('[SW] Fetch failed:', request.url, error);
    // 离线且无缓存时返回 fallback
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Network First 策略：
 * 1. 先尝试从网络获取最新版本
 * 2. 网络不可用时回退到缓存
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.log('[SW] Network unavailable, falling back to cache:', request.url);
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    return new Response('Offline', { status: 503 });
  }
}

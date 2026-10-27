// Offline mock of a German news site with a cookie banner, used only to self-test the pipeline.
// Ground truth: GA loads before consent (a "violation"); ads + Meta load after accept;
// Hotjar loads even after reject.
const page = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Beispiel News</title>
<link rel="stylesheet" href="/static/main.css">
<script src="/static/app.js"></script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TEST"></script>
</head><body>
<h1>Beispiel News</h1>
${Array.from({ length: 30 }, (_, i) => `<p>Artikel ${i} Lorem ipsum dolor sit amet.</p><img src="/img/${i}.jpg" width="300" height="100">`).join('')}
<div id="cookie-banner" role="dialog" aria-label="Cookie-Einstellungen"
     style="position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:2px solid #333;padding:24px;z-index:9999">
  <p>Wir verwenden Cookies und ähnliche Technologien, um Inhalte zu personalisieren und Werbung anzuzeigen.
     Mit „Alle akzeptieren“ stimmen Sie der Verarbeitung Ihrer Daten durch uns und unsere Partner zu.</p>
  <button id="accept">Alle akzeptieren</button>
  <button id="reject">Alle ablehnen</button>
</div>
<script>
  function load(src){ var s=document.createElement('script'); s.src=src; document.head.appendChild(s); }
  function px(src){ new Image().src=src; }
  document.getElementById('accept').onclick=function(){
    document.getElementById('cookie-banner').remove();
    load('https://securepubads.g.doubleclick.net/tag/js/gpt.js');
    load('https://connect.facebook.net/de_DE/fbevents.js');
    px('https://www.facebook.com/tr?id=1&ev=PageView');
    px('https://s2.flylax.com/px.gif');
    load('https://static.criteo.net/js/ld/publishertag.js');
  };
  document.getElementById('reject').onclick=function(){
    document.getElementById('cookie-banner').remove();
    load('https://static.hotjar.com/c/hotjar-1.js');
  };
  px('https://www.google-analytics.com/g/collect?v=2&tid=G-TEST');
</script>
</body></html>`;

const sizes = {
  'googletagmanager.com': 120_000, 'doubleclick.net': 90_000, 'facebook.net': 110_000,
  'criteo.net': 60_000, 'hotjar.com': 40_000, 'app.js': 200_000, 'main.css': 30_000,
};


const aboPage = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Abo News</title>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABO"></script></head><body>
<h1>Abo News</h1>${'<p>Text</p>'.repeat(40)}
<div id="cmp" role="dialog" aria-modal="true" style="position:fixed;inset:10% 20%;background:#fff;border:2px solid #333;padding:24px;z-index:9999">
  <h2>Herzlich willkommen!</h2>
  <p>Mit Werbung und Tracking: Speicherung und Verarbeitung von Daten für personalisierte Werbung mit Drittanbietern.</p>
  <button id="ok">Einwilligen und weiter</button>
  <p>Werbefrei lesen: Nutzen Sie uns kostenpflichtig ganz ohne Werbetracking.</p>
  <button id="abo">Jetzt abonnieren</button>
  <button id="settings">Einstellungen</button>
</div>
<script>
  document.getElementById('ok').onclick=function(){ document.getElementById('cmp').remove();
    var s=document.createElement('script'); s.src='https://securepubads.g.doubleclick.net/tag/js/gpt.js'; document.head.appendChild(s);
    new Image().src='https://www.facebook.com/tr?id=2&ev=PageView'; document.cookie='_fbp=fb.1.123; path=/'; };
</script></body></html>`;

const blockPage = `<!doctype html><html lang="de"><head><title>Zugriff verweigert</title></head><body>
<p>Aus Sicherheitsgründen mussten wir den Zugriff auf unsere Daten leider verweigern.</p></body></html>`;


const spPage = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Iframe News</title></head><body>
<h1>Iframe News</h1>${'<p>Text</p>'.repeat(40)}
<iframe id="sp" src="https://cdn.privacy-mgmt.com/index.html?site=1" style="position:fixed;inset:15% 25%;width:50%;height:60%;border:1px solid #999;background:#fff;z-index:9999"></iframe>
<script>
  window.addEventListener('message', function(e){
    if (e.data==='accept'){ document.getElementById('sp').remove(); new Image().src='https://d5.eu-4-id5-sync.com/'; var s=document.createElement('script'); s.src='https://securepubads.g.doubleclick.net/tag/js/gpt.js'; document.head.appendChild(s); }
    if (e.data==='reject'){ document.getElementById('sp').style.visibility='hidden'; } // like Sourcepoint: hidden, not removed
  });
  new Image().src='https://o1.ingest.sentry.io/api/1/envelope/';
</script></body></html>`;
const spFrame = `<!doctype html><html lang="de"><body style="font-family:sans-serif">
<p>Wir und unsere 185 Partner verwenden Cookies und verarbeiten Daten für personalisierte Werbung.</p>
<button onclick="parent.postMessage('accept','*')">Akzeptieren und weiter</button>
<button onclick="parent.postMessage('reject','*')">Ablehnen</button></body></html>`;


const shadowPage = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Amt</title></head><body>
<h1>Bundesamt</h1>${'<p>Text</p>'.repeat(30)}
<amt-cookie-banner></amt-cookie-banner>
<script>
  class B extends HTMLElement { connectedCallback(){ const r=this.attachShadow({mode:'open'});
    r.innerHTML='<div style="position:fixed;inset:20% 25%;background:#fff;border:1px solid #333;padding:20px">'+
      '<h2>Verwendung von Cookies und anderen Technologien</h2><p>Webanalyse, Personalisierung, Werbung.</p>'+
      '<button id="r">Alle Cookies ablehnen</button> <button>Auswahl bestätigen</button> <button id="a">Alle Cookies akzeptieren</button></div>';
    r.getElementById('a').onclick=()=>{ this.remove(); new Image().src='https://www.google-analytics.com/g/collect?v=2'; new Image().src='https://cm.g.doubleclick.net/pixel?x=1'; };
    r.getElementById('r').onclick=()=>{ this.remove(); }; } }
  customElements.define('amt-cookie-banner', B);
</script></body></html>`;
const inputPage = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Shop</title></head><body>
<form id="sp-cc" style="position:relative;background:#eee;padding:20px">
  <p>Wir verwenden Cookies und ähnliche Tools, um Werbung anzuzeigen und Ihr Einkaufserlebnis zu personalisieren.</p>
  <span class="btn"><input type="submit" id="acc" aria-labelledby="acc-label" style="width:120px;height:30px"><span id="acc-label">Akzeptieren</span></span>
  <span class="btn"><input type="submit" id="rej" aria-labelledby="rej-label" style="width:120px;height:30px"><span id="rej-label">Ablehnen</span></span>
</form>${'<p>Produkt</p>'.repeat(30)}
<script>
  document.getElementById('sp-cc').onsubmit=(e)=>{ e.preventDefault(); const acc=e.submitter && e.submitter.id==='acc';
    document.getElementById('sp-cc').remove(); if(acc){ new Image().src='https://c.amazon-adsystem.com/aax2/apstag.js'; } };
</script></body></html>`;


// Pathological ad loop: thousands of requests with huge query strings and POST bodies (memory stress test).
const floodPage = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Flood</title></head><body><h1>Flood</h1>
<script>
  const big = 'x'.repeat(100000), body = 'y'.repeat(200000);
  let n = 0;
  const fire = () => { for (let i = 0; i < 50; i++) { n++; fetch('https://ads.flood-ads.test/bid?n=' + n + '&d=' + big, { method: 'POST', body }).catch(() => {}); } if (n < 20000) setTimeout(fire, 20); };
  fire();
</script></body></html>`;

export function installMock(context) {
  context.route('**/*', (route) => {
    const url = route.request().url();
    if (url === 'https://www.beispiel-flood.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: floodPage });
    if (url.startsWith('https://ads.flood-ads.test/')) return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    if (url === 'https://www.beispiel-shadow.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: shadowPage });
    if (url === 'https://www.beispiel-input.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: inputPage });
    if (url === 'https://www.beispiel-iframe.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: spPage });
    if (url.startsWith('https://cdn.privacy-mgmt.com/index.html')) return route.fulfill({ status: 200, contentType: 'text/html', body: spFrame });
    if (url === 'https://www.beispiel-abo.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: aboPage });
    if (url === 'https://www.beispiel-block.test/') return route.fulfill({ status: 200, contentType: 'text/html', body: blockPage });
    if (url === 'https://www.haengt-alert.test/') {
      return route.fulfill({ status: 200, contentType: 'text/html',
        body: '<html><body><h1>Alert</h1><img src="/never.gif"><script>setTimeout(()=>alert("Hallo"),1500)</script></body></html>' });
    }
    if (url.endsWith('/never.gif')) return; // never fulfilled: 'load' never fires
    if (url === 'https://www.haengt-loop.test/') {
      return route.fulfill({ status: 200, contentType: 'text/html',
        body: '<html><body><h1>Loop</h1><script>setTimeout(()=>{for(;;){}},2000)</script></body></html>' });
    }
    if (url === 'https://www.beispiel-news.test/') {
      return route.fulfill({ status: 200, contentType: 'text/html', body: page });
    }
    const key = Object.keys(sizes).find((k) => url.includes(k));
    const n = key ? sizes[key] : url.includes('/img/') ? 15_000 : 43;
    const isJs = url.includes('.js') || url.includes('gtag');
    return route.fulfill({
      status: 200,
      contentType: isJs ? 'application/javascript' : url.endsWith('.css') ? 'text/css' : 'image/gif',
      body: isJs ? '/*' + 'x'.repeat(n) + '*/' : 'x'.repeat(n),
    });
  });
}

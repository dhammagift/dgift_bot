// Prints the Uposatha days (by the suttas: 8th/14th/15th of each half) for the next N days as plain text.
// Usage: node upo.js <ru|en> <tz> <days> [lat lon [place]]; the day runs sunset to sunset at the place given, and without
// one at Bodh Gaya (the demo's own place: the same real sunrise and sunset, not a blank 18:00) — the rule the page and the
// apps use, so a city's list here and its calendar in the app agree (Moscow's 8th is the 2nd of October when its last
// quarter comes before that day's sunset, Almaty's is the 3rd).
// The calendar link is not part of the text: the bot puts it on a button under the message.
// With a place the list is a <pre> table (Telegram has no tables; monospace is the only way to line the columns up),
// without one there is nothing to align and the plain list stays as it is. Sent with parse_mode=HTML.
const A = require('/var/www/dg-node-prod/public/overrides/js/vendor/astronomy.browser.min.js');
const C = require('/var/www/dg-node-prod/public/overrides/js/uposatha-core.js');
const [lang = 'ru', tzArg = 'Asia/Kolkata', days = '30', lat, lon, place] = process.argv.slice(2);
const ru = lang === 'ru';
const t = C.NAMES[ru ? 'ru' : 'en'];
// The demo's place, and the reference the site itself calls Bodh Gaya: a real place with real times, so the default answer
// shows the same four moments as a city does. The moon is one, and the day is the evening at wherever it is read.
const DEFAULT_PLACE = { name: 'Bodh Gaya', lat: 24.6961, lon: 84.9866, tz: 'Asia/Kolkata' };
const given = lat && lon ? { name: place || tzArg, lat: +lat, lon: +lon, tz: tzArg } : DEFAULT_PLACE;
const loc = { lat: given.lat, lon: given.lon }, tz = given.tz;
const today = C.localDay(new Date(), tz), to = C.ymdAdd(today, +days);
const WD = (ru ? 'вс пн вт ср чт пт сб' : 'Sun Mon Tue Wed Thu Fri Sat').split(' ');
const SHORT = new Intl.DateTimeFormat(ru ? 'ru' : 'en', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const HM = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: tz });
const obs = new A.Observer(loc.lat, loc.lon, 0);
const rows = C.dataset(today, to, { tz, sutta: true, loc }).rows.filter(r => r.uposatha);
const where = given.name;
const head = ru ? `Упосатха по суттам на ближайшие ${days} дней (${where}):`
  : `Uposatha by the suttas for the next ${days} days (${where}):`;
// Telegram parses the message as HTML: a city name with & or < must not break it.
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const items = rows.map(r => {
  const n = C.dayNo(r.names[r.names.length - 1]), waning = r.names[0] > 15;
  const moon = n === 15 ? (waning ? '🌑' : '🌕') : n === 8 ? (waning ? '🌗' : '🌓') : (waning ? '🌘' : '🌔');
  const begin = C.sunEvent('set', r.y, r.m, r.d, tz, obs);
  const dawn = C.sunEvent('rise', r.y, r.m, r.d + 1, tz, obs);
  const end = C.sunEvent('set', r.y, r.m, r.d + 1, tz, obs);
  const noon = A.SearchHourAngle('Sun', obs, 0, C.zonedToUtc(r.y, r.m, r.d + 1, 0, tz)).time.date;
  return {
    moon: moon,
    ymd: r.ymd,
    dow: r.dow,
    date: SHORT.format(new Date(r.ymd)).replace(/\.$/, '') + ', ' + WD[r.dow],
    name: r.names.map(x => t.nth(C.dayNo(x))).join(t.and),
    times: begin && end ? [begin, dawn, noon, end].filter(Boolean).map(d => HM.format(d)).join(' · ') : '',
  };
});

// Plain text on purpose: any fixed-width block (Telegram has only <pre> and <code>) is drawn in a smaller
// face than the message text. The columns are not padded here — a proportional font cannot line them up.
const out = items.map(i => `${i.moon} ${i.date} — ${i.name}${i.times ? ' · ' + i.times : ''}`).join('\n');
const legend = ru ? 'Время: начало · рассвет · полдень · конец' : 'Times: begin · dawn · noon · end';

console.log([esc(head), '', esc(out), '', legend].join('\n'));

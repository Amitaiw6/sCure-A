// The "Send Simulated Print" list offers every program the machine has: its own, then the built-in catalog
// (user, 2026-11-03: it showed 4 user programs and none of the 19 catalog ones). An older machine sends no catalog.
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/Page.html', 'utf8');
const pick = re => { const m = src.match(re); if (!m) throw new Error('not found: ' + re); return m[0]; };
const escH = eval(pick(/const escH = [^\n]+/).replace(/^const escH = /, '').replace(/;$/, ''));
const programOptions = eval('(' + pick(/function programOptions\(m\) \{[\s\S]*?\n\}/) + ')');
let n = 0, bad = 0;
const ok = (c, msg) => { n++; if (!c) { bad++; console.log('FAIL', msg); } };

const both = programOptions({ programs: [{ name: '450' }], presets: [{ name: 'RG 3280' }, { name: 'ST45 <Elastic>' }] });
ok(both.includes('<optgroup label="My programs"><option>450</option></optgroup>'), 'user programs first, in their own group');
ok(both.includes('<optgroup label="Catalog"><option>RG 3280</option>'), 'catalog listed');
ok(both.includes('ST45 &lt;Elastic&gt;'), 'names are escaped');
ok((both.match(/<option>/g) || []).length === 3, 'every program once');

const old = programOptions({ programs: [{ name: '450' }, { name: 'bleach' }] });
ok(old === '<option>450</option><option>bleach</option>', 'an older machine (no catalog) looks as before');
const onlyCat = programOptions({ presets: [{ name: 'RG 3280' }] });
ok(!onlyCat.includes('My programs') && onlyCat.includes('RG 3280'), 'no empty user group');
ok(/presets: s\.presets \|\| \[\]/.test(fs.readFileSync(__dirname + '/Code.gs', 'utf8')), 'Code.gs passes the catalog to the page');

// the NFC tag field: typed any way, sent one way; a non-UID is refused before it reaches the machine
const nfcTagOf = eval('(' + pick(/function nfcTagOf\(text\) \{[\s\S]*?\n\}/) + ')');
for (const typed of ['e007c0e19393186d', 'E0 07 C0 E1 93 93 18 6D', 'e0:07:c0:e1:93:93:18:6d', ' E0-07-C0-E1-93-93-18-6D '])
  ok(nfcTagOf(typed) === 'E0:07:C0:E1:93:93:18:6D', 'tag typed as ' + JSON.stringify(typed));
for (const typed of ['', 'not a tag', 'E007C', 'E0', 'E007C0E19393186DE007C0E19393186DAA'])
  ok(nfcTagOf(typed) === null, 'not a tag: ' + JSON.stringify(typed));
ok(/payload\.nfcTag = tag/.test(src) && /id="nfc-\$\{i\}"/.test(src), 'the send form has the tag field and sends it');

// the machine card: catalog table (read-only) and a Delete on every recent print (user, 2026-11-03)
{
  const SEARCH = '';
  const fmtAgo = () => 'now', netbirdPill = () => '', cureRows = () => '';
  let ME = { canAdmin: true };
  const removeMachineBlock = eval('(' + pick(/function removeMachineBlock\(m, i\) \{[\s\S]*?\n\}/) + ')');
  const machineCard = eval('(' + pick(/function machineCard\(m, i\) \{[\s\S]*?\n\}/) + ')');
  // remove a retired machine (user, 2026-11-11): admins only, only a machine with no key, password field + Remove
  const retired = machineCard({ name: 'SC0003', retired: true, state: {}, programs: [], prints: [] }, 4);
  ok(retired.includes('data-rmmachine="4"') && retired.includes('Remove SC0003'), 'a retired machine has a Remove button for an admin');
  ok(/id="rmpw-4" type="password"/.test(retired), 'Remove asks for the portal password in a password field');
  ok(!machineCard({ name: 'CureBox-3', retired: false, state: {}, programs: [], prints: [] }, 5).includes('data-rmmachine'), 'a machine with a key has no Remove');
  ME = { canAdmin: false };
  ok(!machineCard({ name: 'SC0003', retired: true, state: {}, programs: [], prints: [] }, 4).includes('data-rmmachine'), 'not an admin: no Remove');
  ME = null;
  ok(!machineCard({ name: 'SC0003', retired: true, state: {}, programs: [], prints: [] }, 4).includes('data-rmmachine'), 'signed out: no Remove');
  ME = { canAdmin: true };
  ok(/portalMachineRemove', tok\(\), body\.name \|\| '', body\.password \|\| ''/.test(src), 'the page bridge passes name and password');
  ok(/if \(!pw\) \{/.test(src) && /confirm\(`Remove \$\{m\.name\} from sCure Cloud\?/.test(src), 'empty password stopped; asks once before removing');
  const html = machineCard({ name: 'CureBox-2', online: true, state: {},
    programs: [{ id: 'u1', name: '450', steps: [{}], totalDuration: 10 }],
    presets: [{ id: 'p1', name: 'Ultracur3D ST45', steps: [{}, {}], totalDuration: 42 }],
    prints: [{ id: 'pr-1', printName: 'Job <1>', materialName: '450', printerName: 'TZ', status: 'completed', nfcTag: 'E0:07:C0:E1:93:93:99:40' }] }, 0);
  const cat = html.slice(html.indexOf('Machine Catalog'), html.indexOf('Send Simulated Print'));
  ok(cat.includes('Ultracur3D ST45') && cat.includes('2 steps') && cat.includes('42 min'), 'catalog table lists the built-in programs');
  ok(!/data-(edit|del)=/.test(cat), 'catalog rows cannot be edited or deleted');
  ok(cat.includes('1 programs') || cat.includes('built in'), 'catalog heading counts the programs');
  ok(html.includes('data-delprint="0:pr-1"'), 'every recent print has a Delete');
  ok(html.includes('Job &lt;1&gt;') && html.includes('tag E0:07:C0:E1:93:93:99:40'), 'print shows its tag, names escaped');
  const none = machineCard({ name: 'Old', state: {}, programs: [], prints: [] }, 1);
  ok(none.includes('needs firmware 1.0.145'), 'an older machine says why the catalog is empty');
  ok(/COMMAND_TYPES = \[[^\]]*'delete_print'/.test(fs.readFileSync(__dirname + '/Code.gs', 'utf8')), 'the server accepts delete_print');
}

// "I did it" on a DVT run (user, 2026-11-12): the box is redrawn every second, so the press goes at pointerdown and the
// step it was sent for stays "Sent…" across redraws - once - until the step changes or 8 s pass
{
  const lf = src.replace(/\r\n/g, '\n');
  const wire = (lf.match(/  const did = box\.querySelector\('\[data-dvt-acted\]'\);[\s\S]*?\n    did\.onclick = send;\n  \}/) || [''])[0];
  ok(wire, 'the I-did-it wiring is found in Page.html');
  const sent = [];
  const dvtSend = (path, body) => sent.push([path, body.id]);
  const mk = () => ({ dataset: { dvtActed: '24' }, disabled: false, textContent: 'I did it' });
  const g = {};
  const draw = (act) => { const btn = mk(); const box = { querySelector: () => btn }; const r = { id: 24, act };
                          new Function('box', 'r', 'g', 'dvtSend', wire)(box, r, g, dvtSend); return btn; };
  const open = { text: 'OPEN THE DOOR and keep it open' };
  let b = draw(open);
  ok(typeof b.onpointerdown === 'function', 'the press is sent on pointerdown, before a redraw can swap the button');
  b.onpointerdown({ preventDefault() {} });
  ok(sent.length === 1 && sent[0][0] === '/api/dvt/acted' && sent[0][1] === 24, 'pointerdown sends the press for that run');
  b.onclick({});
  ok(sent.length === 1, 'the click that follows does not send it twice');
  b = draw(open);
  ok(b.disabled && b.textContent === 'Sent…', 'the redrawn button still shows Sent…');
  b.onpointerdown({}); ok(sent.length === 1, 'and does not send again');
  b = draw({ text: 'HOLD THE MAGNET against the door sensor' });
  ok(!b.disabled && b.textContent === 'I did it', 'the next step gets a fresh button');
  b.onclick({}); ok(sent.length === 2, 'a plain click (keyboard) still sends');
  g.sentAt -= 9000; b = draw({ text: 'HOLD THE MAGNET against the door sensor' });
  ok(!b.disabled, 'no answer for 8 s: the button can be pressed again');
}

console.log(bad ? `${bad} of ${n} FAILED` : `ALL PASSED (${n} checks)`);
process.exit(bad ? 1 : 0);

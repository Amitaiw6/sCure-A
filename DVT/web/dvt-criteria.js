// pass_criteria evaluator - same grammar and verdicts as DVT/dvt_tool/criteria.py:
// AND / OR / NOT, ( ), == != < <= > >=, + - * /, abs / max / min, field names,
// dotted threshold names, numbers, 'strings', true / false / null.
// No short-circuit: every referenced value must exist, else BLOCKED (never a silent PASS).
(function (root) {
  'use strict';

  class Missing extends Error { constructor(name) { super(name); this.missing = name; } }
  class Blocked extends Error {}

  function tokenize(src) {
    const out = [];
    const re = /\s*(?:(\d+(?:\.\d+)?)|'([^']*)'|"([^"]*)"|([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)|(==|!=|<=|>=|[<>()+\-*/,]))/y;
    let i = 0;
    while (i < src.length) {
      if (/^\s*$/.test(src.slice(i))) break;
      re.lastIndex = i;
      const m = re.exec(src);
      if (!m) throw new SyntaxError('cannot parse pass_criteria near: ' + src.slice(i, i + 20));
      i = re.lastIndex;
      if (m[1] !== undefined) out.push({ t: 'num', v: Number(m[1]) });
      else if (m[2] !== undefined || m[3] !== undefined) out.push({ t: 'str', v: m[2] !== undefined ? m[2] : m[3] });
      else if (m[4] !== undefined) {
        const w = m[4];
        if (w === 'AND' || w === 'OR' || w === 'NOT') out.push({ t: 'op', v: w });
        else if (w === 'true' || w === 'false') out.push({ t: 'lit', v: w === 'true' });
        else if (w === 'null') out.push({ t: 'lit', v: null });
        else out.push({ t: 'name', v: w });
      } else out.push({ t: 'op', v: m[5] });
    }
    return out;
  }

  function parse(src) {
    const toks = tokenize(src);
    let p = 0;
    const peek = () => toks[p];
    const isOp = (v) => peek() && peek().t === 'op' && peek().v === v;
    const expect = (v) => { if (!isOp(v)) throw new SyntaxError(`expected ${v}`); p++; };

    function orExpr() {
      const parts = [andExpr()];
      while (isOp('OR')) { p++; parts.push(andExpr()); }
      return parts.length === 1 ? parts[0] : { k: 'or', parts };
    }
    function andExpr() {
      const parts = [notExpr()];
      while (isOp('AND')) { p++; parts.push(notExpr()); }
      return parts.length === 1 ? parts[0] : { k: 'and', parts };
    }
    function notExpr() {
      if (isOp('NOT')) { p++; return { k: 'not', a: notExpr() }; }
      return compare();
    }
    function compare() {
      const first = sum();
      const chain = [];
      while (peek() && peek().t === 'op' && ['==', '!=', '<', '<=', '>', '>='].includes(peek().v)) {
        const op = toks[p++].v;
        chain.push([op, sum()]);
      }
      return chain.length ? { k: 'cmp', first, chain } : first;
    }
    function sum() {
      let a = product();
      while (isOp('+') || isOp('-')) { const op = toks[p++].v; a = { k: 'bin', op, a, b: product() }; }
      return a;
    }
    function product() {
      let a = unary();
      while (isOp('*') || isOp('/')) { const op = toks[p++].v; a = { k: 'bin', op, a, b: unary() }; }
      return a;
    }
    function unary() {
      if (isOp('-')) { p++; return { k: 'neg', a: unary() }; }
      return atom();
    }
    function atom() {
      const tk = toks[p++];
      if (!tk) throw new SyntaxError('unexpected end of pass_criteria');
      if (tk.t === 'num' || tk.t === 'str' || tk.t === 'lit') return { k: 'const', v: tk.v };
      if (tk.t === 'op' && tk.v === '(') { const e = orExpr(); expect(')'); return e; }
      if (tk.t === 'name') {
        if (isOp('(')) {
          if (!['abs', 'max', 'min'].includes(tk.v)) throw new SyntaxError('only abs/max/min may be called');
          p++;
          const args = [];
          if (!isOp(')')) { args.push(orExpr()); while (isOp(',')) { p++; args.push(orExpr()); } }
          expect(')');
          return { k: 'call', f: tk.v, args };
        }
        return tk.v.includes('.') ? { k: 'thr', path: tk.v } : { k: 'field', name: tk.v };
      }
      throw new SyntaxError('unexpected ' + tk.v);
    }

    const tree = orExpr();
    if (p !== toks.length) throw new SyntaxError('unexpected ' + toks[p].v);
    return tree;
  }

  function num(v) {
    if (typeof v === 'number') return v;
    if (typeof v === 'boolean') return v ? 1 : 0;
    throw new Blocked('not a number: ' + JSON.stringify(v));
  }

  function eq(a, b) {
    if (typeof a === 'boolean' || typeof b === 'boolean') {
      if ((typeof a === 'boolean' || typeof a === 'number') && (typeof b === 'boolean' || typeof b === 'number')) return num(a) === num(b);
    }
    return a === b;
  }

  function order(op, a, b) {
    const bothStr = typeof a === 'string' && typeof b === 'string';
    if (!bothStr) { a = num(a); b = num(b); }
    return op === '<' ? a < b : op === '<=' ? a <= b : op === '>' ? a > b : a >= b;
  }

  function run(node, values, thresholds) {
    switch (node.k) {
      case 'const': return node.v;
      case 'field': {
        const v = values[node.name];
        if (v === undefined || v === null || v === '') throw new Missing(node.name);
        return v;
      }
      case 'thr': {
        let cur = thresholds;
        for (const part of node.path.split('.')) cur = cur && typeof cur === 'object' ? cur[part] : undefined;
        if (cur === undefined || cur === null) throw new Missing(node.path);
        return cur;
      }
      case 'and': { const vs = node.parts.map((x) => run(x, values, thresholds)); return vs.every(Boolean); }
      case 'or': { const vs = node.parts.map((x) => run(x, values, thresholds)); return vs.some(Boolean); }
      case 'not': return !run(node.a, values, thresholds);
      case 'neg': return -num(run(node.a, values, thresholds));
      case 'bin': {
        const a = run(node.a, values, thresholds), b = run(node.b, values, thresholds);
        if (node.op === '+' && typeof a === 'string' && typeof b === 'string') return a + b;
        const x = num(a), y = num(b);
        if (node.op === '/' && y === 0) throw new Blocked('division by zero');
        return node.op === '+' ? x + y : node.op === '-' ? x - y : node.op === '*' ? x * y : x / y;
      }
      case 'call': {
        const args = node.args.map((x) => num(run(x, values, thresholds)));
        if (node.f === 'abs') { if (args.length !== 1) throw new Blocked('abs takes one value'); return Math.abs(args[0]); }
        if (!args.length) throw new Blocked(node.f + ' of nothing');
        return node.f === 'max' ? Math.max(...args) : Math.min(...args);
      }
      case 'cmp': {
        let left = run(node.first, values, thresholds);
        let ok = true;
        for (const [op, expr] of node.chain) {
          const right = run(expr, values, thresholds);
          const r = op === '==' ? eq(left, right) : op === '!=' ? !eq(left, right) : order(op, left, right);
          if (!r) ok = false;
          left = right;
        }
        return ok;
      }
      default: throw new SyntaxError('bad node');
    }
  }

  function names(node, out = new Set()) {
    if (!node || typeof node !== 'object') return out;
    if (node.k === 'field') out.add(node.name);
    if (node.k === 'thr') out.add(node.path);
    for (const key of ['a', 'b', 'first']) if (node[key]) names(node[key], out);
    for (const key of ['parts', 'args']) if (node[key]) node[key].forEach((x) => names(x, out));
    if (node.chain) node.chain.forEach(([, e]) => names(e, out));
    return out;
  }

  /** Returns { verdict: 'PASS' | 'FAIL' | 'BLOCKED', detail }. Throws SyntaxError only for a malformed expression. */
  function evaluate(expr, values, thresholds) {
    const tree = parse(expr);
    try {
      return { verdict: run(tree, values || {}, thresholds || {}) ? 'PASS' : 'FAIL', detail: '' };
    } catch (e) {
      if (e instanceof Missing) return { verdict: 'BLOCKED', detail: 'missing value: ' + e.missing };
      if (e instanceof Blocked) return { verdict: 'BLOCKED', detail: 'cannot evaluate: ' + e.message };
      throw e;
    }
  }

  const api = { evaluate, parse, referencedNames: (expr) => [...names(parse(expr))] };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.DVT_CRITERIA = api;
})(typeof window !== 'undefined' ? window : globalThis);

// Runs inside the page via the browser driver's evaluate.
//
// Returns aggregates, not per-element dumps: the set of colors/sizes/spacings
// the page actually uses, which of them fall outside the project's tokens, and
// the handful of things an eye cannot measure — contrast ratios, target sizes,
// clipped content. A few KB, readable as-is.
//
// Values on both sides are normalized by the engine itself: a probe element
// takes the raw declaration and getComputedStyle hands back the canonical form,
// with var() chains resolved. Colors go through a canvas pixel so oklch(),
// color-mix() and anything the browser adds later all land in sRGB.
//
// Input: { tokens: ["--color-primary", ...], rootSelector?, limit? }
// Output: see references/data-format.md

;(function (CFG) {
  const cfg = CFG || {}
  const root = document.querySelector(cfg.rootSelector || 'body')
  if (!root) return { error: `rootSelector matched nothing: ${cfg.rootSelector}` }
  const limit = cfg.limit || 1500

  const probe = document.createElement('div')
  probe.style.cssText = 'position:absolute!important;top:-9999px;left:-9999px;visibility:hidden;pointer-events:none'
  document.documentElement.appendChild(probe)

  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 1
  const ctx = canvas.getContext('2d', { willReadFrequently: true })

  function toRgb(s) {
    if (!s || s === 'none') return null
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillStyle = '#000000'
    const before = ctx.fillStyle
    ctx.fillStyle = s
    if (ctx.fillStyle === before && !/^(#000000|#000|black|rgba?\(\s*0\s*,\s*0\s*,\s*0\s*(,\s*1\s*)?\))$/i.test(s.trim())) return null
    ctx.fillRect(0, 0, 1, 1)
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
    return { r, g, b, a: a / 255 }
  }

  // --- tokens ---------------------------------------------------------------

  // The declaration is assigned directly so CSSOM does the syntax check: a
  // length written into `color` is rejected and `style.color` stays empty.
  // Assigning `var(--x)` would be accepted for every property regardless of type.
  function tryAs(prop, declared) {
    probe.style[prop] = ''
    probe.style[prop] = declared
    if (!probe.style[prop]) return null
    const got = getComputedStyle(probe)[prop]
    probe.style[prop] = ''
    return got
  }

  // A ratio like `1.5` is a valid font-weight, so line-height tokens have to be
  // recognised by shape before the property probes run, or they come back typed
  // as a weight and never match the px value an element computes.
  function resolveToken(name) {
    const declared = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    if (!declared) return { name, declared: '', kind: 'unresolved', value: null }
    if (/^-?[\d.]+$/.test(declared) && parseFloat(declared) < 5) {
      return { name, declared, kind: 'ratio', value: parseFloat(declared) }
    }
    // shadcn/ui and its descendants store colors as bare channel triplets
    // (`222.2 47.4% 11.2%`) and wrap them at the use site with `hsl(var(--x))`.
    // CSSOM rejects the bare form, so without the second attempt every token in
    // such a project reads as unresolved and the whole page turns into
    // off-token candidates.
    const color = tryAs('color', declared) || tryAs('color', `hsl(${declared})`)
    if (color) return { name, declared, kind: 'color', value: color }
    const length = tryAs('width', declared)
    if (length) return { name, declared, kind: 'length', value: length }
    const weight = tryAs('fontWeight', declared)
    if (weight) return { name, declared, kind: 'weight', value: weight }
    const family = tryAs('fontFamily', declared)
    if (family) return { name, declared, kind: 'family', value: family }
    const shadow = tryAs('boxShadow', declared)
    if (shadow) return { name, declared, kind: 'shadow', value: shadow }
    return { name, declared, kind: 'unresolved', value: null }
  }

  const tokens = (cfg.tokens || []).map(resolveToken)
  const allowed = new Set(tokens.filter((t) => t.value !== null && t.kind !== 'ratio').map((t) => String(t.value)))
  const ratios = tokens.filter((t) => t.kind === 'ratio').map((t) => t.value)

  // --- elements -------------------------------------------------------------

  function describe(el) {
    let s = el.tagName.toLowerCase()
    if (el.id) return s + '#' + el.id
    const cls = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2)
    if (cls.length) s += '.' + cls.join('.')
    const sibs = el.parentElement ? [...el.parentElement.children].filter((c) => c.tagName === el.tagName) : []
    if (sibs.length > 1) s += `:nth-of-type(${sibs.indexOf(el) + 1})`
    return s
  }

  // A zero on either axis paints nothing.
  function visible(el) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 || r.height === 0) return false
    const cs = getComputedStyle(el)
    return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0'
  }

  // The root itself is not matched by its own descendant query, and it is where
  // a page-wide font and text color usually live.
  const all = [root, ...root.querySelectorAll('*')]
  const shown = all.filter(visible).slice(0, limit)

  // --- what the page uses ---------------------------------------------------

  const seen = { color: new Map(), fontSize: new Map(), fontFamily: new Map(), fontWeight: new Map(), spacing: new Map(), radius: new Map(), shadow: new Map(), duration: new Map() }

  const SKIP = new Set(['none', 'normal', 'auto', '0px', '0s', 'rgba(0, 0, 0, 0)'])

  // The true count drives the "high count on one selector prefix means it came
  // from a component library" heuristic; samples stay capped so the payload
  // does not grow with the page.
  function note(bucket, value, sel) {
    if (!value || SKIP.has(value)) return
    if (!seen[bucket].has(value)) seen[bucket].set(value, { count: 0, sample: [] })
    const e = seen[bucket].get(value)
    e.count++
    if (e.sample.length < 3) e.sample.push(sel)
  }

  let shadowRoots = 0
  let frames = 0
  // Repeated components produce identical rows; keyed accumulation collapses
  // "40 table links at 20x20" into one line with a count.
  const rows = { contrast: new Map(), contrastUnknown: new Map(), targets: new Map(), clipped: new Map() }
  function add(kind, key, row) {
    if (!rows[kind].has(key)) rows[kind].set(key, { ...row, count: 0, sample: [] })
    const e = rows[kind].get(key)
    e.count++
    if (e.sample.length < 3) e.sample.push(row.sel)
  }

  for (const el of shown) {
    const cs = getComputedStyle(el)
    const sel = describe(el)
    if (el.shadowRoot) shadowRoots++
    if (el.tagName === 'IFRAME' || el.tagName === 'FRAME') frames++

    note('color', cs.color, sel)
    note('color', cs.backgroundColor, sel)
    note('fontSize', cs.fontSize, sel)
    note('fontFamily', cs.fontFamily, sel)
    note('fontWeight', cs.fontWeight, sel)
    note('shadow', cs.boxShadow, sel)
    note('duration', cs.transitionDuration, sel)
    for (const p of ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginTop', 'marginBottom', 'rowGap', 'columnGap']) note('spacing', cs[p], sel)
    note('radius', cs.borderTopLeftRadius, sel)

    const r = el.getBoundingClientRect()
    const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    if (ownText) {
      const fg = toRgb(cs.color)
      const bg = backdrop(el)
      if (!fg || !bg) {
        add('contrastUnknown', `${cs.color}|${!fg}`, { sel, color: cs.color, reason: !fg ? 'foreground unparseable' : 'backdrop is an image or gradient' })
      } else if (fg.a > 0) {
        const merged = over(fg, bg)
        const ratio = contrastRatio(merged, bg)
        const size = parseFloat(cs.fontSize)
        const large = size >= 24 || (size >= 18.66 && parseInt(cs.fontWeight, 10) >= 700)
        const need = large ? 3 : 4.5
        if (ratio < need) add('contrast', `${ratio}|${need}|${cs.color}|${rgbStr(bg)}`, { sel, ratio, need, fontSize: cs.fontSize, color: cs.color, bg: rgbStr(bg) })
      }
    }

    // WCAG 2.2 SC 2.5.8 is 24x24 at AA; 44 is SC 2.5.5 at AAA. Its Inline
    // exception covers a target "in a sentence", which is a parent carrying its
    // own text around the link — not `display: inline`. An icon link written as
    // `<a><svg/></a>` computes to inline and is not in any sentence, and keying
    // off display would drop exactly that case.
    const interactive = el.matches('a[href],button,input,select,textarea,[role=button],[role=link],[tabindex]:not([tabindex="-1"])')
    if (interactive && (r.width < 24 || r.height < 24) && !inSentence(el)) {
      add('targets', `${Math.round(r.width)}x${Math.round(r.height)}`, { sel, w: Math.round(r.width), h: Math.round(r.height) })
    }

    if (el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'auto' && cs.overflowX !== 'scroll') {
      add('clipped', `${el.scrollWidth}|${el.clientWidth}`, { sel, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth })
    }
  }

  function inSentence(el) {
    const p = el.parentElement
    if (!p) return false
    return [...p.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1)
  }

  function rgbStr(c) {
    return `rgb(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)})`
  }

  function over(fg, bg) {
    if (fg.a >= 1) return fg
    return { r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 }
  }

  function luminance({ r, g, b }) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }

  function contrastRatio(fg, bg) {
    const a = luminance(fg), b = luminance(bg)
    const [hi, lo] = a > b ? [a, b] : [b, a]
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100
  }

  // Returns null when the backdrop is an image or gradient — it has no single
  // value to measure against, and guessing white yields a confident wrong ratio.
  function backdrop(el) {
    let node = el
    while (node && node !== document.documentElement) {
      const cs = getComputedStyle(node)
      if (cs.backgroundImage !== 'none') return null
      const c = toRgb(cs.backgroundColor)
      if (c && c.a >= 1) return c
      if (c && c.a > 0) {
        const under = node.parentElement ? backdrop(node.parentElement) : null
        return under ? over(c, under) : null
      }
      node = node.parentElement
    }
    const rootCs = getComputedStyle(document.documentElement)
    if (rootCs.backgroundImage !== 'none') return null
    const rootBg = toRgb(rootCs.backgroundColor)
    return rootBg && rootBg.a >= 1 ? rootBg : { r: 255, g: 255, b: 255, a: 1 }
  }

  // --- off-token ------------------------------------------------------------

  // A bucket where nothing matched means the token set has no entry of that
  // type — a Tailwind project defines no spacing custom properties, so every
  // spacing value on the page would otherwise be listed as a candidate. Saying
  // "not compared" once beats emitting a hundred rows nobody can act on.
  const offToken = {}
  const notCompared = []
  for (const [bucket, m] of Object.entries(seen)) {
    const rows = []
    let matched = 0
    for (const [value, e] of m) {
      if (allowed.has(value)) { matched++; continue }
      rows.push({ value, count: e.count, sample: e.sample })
    }
    if (!rows.length) continue
    if (matched === 0) notCompared.push(bucket)
    else offToken[bucket] = rows
  }

  probe.remove()

  const used = {}
  for (const [bucket, m] of Object.entries(seen)) used[bucket] = [...m.keys()].sort()

  return {
    url: location.href,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    sampled: shown.length,
    truncated: all.filter(visible).length > limit,
    unreachable: { shadowRoots, frames },
    tokens: { resolved: tokens.filter((t) => t.value !== null).length, total: tokens.length, ratios, list: tokens },
    used,
    offToken,
    notCompared,
    checks: {
      contrast: [...rows.contrast.values()],
      contrastUnknown: [...rows.contrastUnknown.values()],
      targets: [...rows.targets.values()],
      clipped: [...rows.clipped.values()],
      documentOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
      viewportUserScalable: !/user-scalable\s*=\s*no|maximum-scale\s*=\s*1/.test(document.querySelector('meta[name=viewport]')?.content || ''),
    },
  }
})(CONFIG)

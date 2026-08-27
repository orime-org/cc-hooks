#!/usr/bin/env node
// Runs inject-collect.js against a real page in a real browser and asserts the
// results. Serves the fixture over HTTP because computed styles and the UA
// stylesheet behave differently under file://.
//
// Prints one line per assertion, exits non-zero on any failure.
// Reachable through: python3 tests/smoke-visual-adversary.py

const fs = require('fs')
const http = require('http')
const path = require('path')
const { execSync } = require('child_process')

const INJECT = path.join(__dirname, '..', 'watcher', 'skills', 'visual-adversary', 'scripts', 'inject-collect.js')

const TOKEN_NAMES = [
  '--brand', '--broken', '--gap-4', '--lh-normal', '--never-declared',
  '--pure-black', '--radius-none', '--shadcn', '--shadow-sm', '--stack', '--weight-bold',
]

// Each token exercises one branch of resolveToken. --lh-normal is the one that
// used to come back typed as a font-weight, because 1.5 is a valid weight.
// body carries a hardcoded color: the most common way a page goes off-token.
const FIXTURE = `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {
  --brand: #2563eb;
  --gap-4: 1rem;
  --lh-normal: 1.5;
  --pure-black: #000;
  --radius-none: 0px;
  --shadow-sm: rgba(0, 0, 0, 0.2) 0px 1px 2px 0px;
  --stack: Verdana, sans-serif;
  --weight-bold: 700;
  --broken: var(--nope);
  --shadcn: 222.2 47.4% 11.2%;
}
body { margin:0; background:#fff; color: rgb(17, 17, 17); font-family: Georgia; }
.ok       { background: var(--brand); color:#fff; padding: var(--gap-4); border:0; }
.offbyone { background: rgb(37,99,236); color:#fff; padding: 13px; border:0; }
.faint    { color: rgba(0,0,0,0.25); background:#fff; font-size:14px; }
.oklch    { color: oklch(0.75 0.12 250); background: rgb(255,255,255); }
.ongrad   { background: linear-gradient(#111,#333); color:#fff; padding:9px; }
.icon     { width:20px; height:20px; padding:0; }
.wrap     { width:200px; overflow:hidden; } .wide { width:400px; }
.nav      { display:block }
.nav a    { width:20px; height:20px }
#scoped   { padding: 21px }
</style></head><body>
  <button class="ok">on token</button>
  <button class="offbyone">off by one</button>
  <p class="faint">semi transparent text</p>
  <p class="oklch">oklch text</p>
  <div class="ongrad">text on a gradient</div>
  <p>a sentence with an <a href="#">inline link</a> inside it.</p>
  <button class="icon">x</button>
  <div class="wrap"><div class="wide">overflowing content</div></div>
  <nav class="nav"><a href="#"><svg width="20" height="20"></svg></a></nav>
  <div id="scoped"><p class="inner">inside</p></div>
  <div id="host"></div>
  <iframe title="frame" srcdoc="<p>in a frame</p>"></iframe>
  <script>document.getElementById('host').attachShadow({mode:'open'}).innerHTML='<p>in shadow</p>'</script>
</body></html>`

function resolvePlaywright() {
  const candidates = ['playwright']
  try {
    const globalRoot = execSync('npm root -g', { encoding: 'utf8' }).trim()
    candidates.push(path.join(globalRoot, '@playwright', 'mcp', 'node_modules', 'playwright'))
    candidates.push(path.join(globalRoot, 'playwright'))
  } catch {}
  for (const c of candidates) {
    try {
      return require(require.resolve(c, { paths: [__dirname, process.cwd()] }))
    } catch {}
  }
  return null
}

// The pinned build is often absent while neighbouring ones sit in the cache, and
// downloading one on a check run would turn a verification into a network install.
function cachedHeadlessShell() {
  const home = process.env.HOME || require('os').homedir()
  const roots = [
    path.join(home, 'Library', 'Caches', 'ms-playwright'),
    path.join(home, '.cache', 'ms-playwright'),
    path.join(home, 'AppData', 'Local', 'ms-playwright'),
  ]
  let best = null
  for (const root of roots) {
    let entries
    try { entries = fs.readdirSync(root) } catch { continue }
    for (const e of entries) {
      const m = e.match(/^chromium_headless_shell-(\d+)$/)
      if (!m) continue
      for (const sub of ['chrome-headless-shell-mac-arm64', 'chrome-headless-shell-mac-x64', 'chrome-headless-shell-linux64', 'chrome-headless-shell-win64']) {
        const bin = path.join(root, e, sub, sub.includes('win') ? 'chrome-headless-shell.exe' : 'chrome-headless-shell')
        if (fs.existsSync(bin) && (!best || Number(m[1]) > best.rev)) best = { rev: Number(m[1]), bin }
      }
    }
  }
  return best
}

let browserRevision = 'pinned'

async function launch(pw) {
  try {
    return await pw.chromium.launch()
  } catch (e) {
    // Only a missing executable is recoverable. Catching everything would hide a
    // crash or a sandbox denial behind a retry that reports the same failure.
    if (!/Executable doesn't exist/i.test(String(e && e.message))) throw e
    const cached = cachedHeadlessShell()
    if (!cached) throw e
    browserRevision = `cached-${cached.rev}`
    console.log(`  note: pinned build missing, using cached revision ${cached.rev}`)
    return await pw.chromium.launch({ executablePath: cached.bin })
  }
}

function serve(inject) {
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/inject.js')) {
      res.writeHead(200, { 'Content-Type': 'application/javascript' })
      res.end(inject)
    } else {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      res.end(FIXTURE)
    }
  })
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)))
}

const failures = []
function check(name, cond, detail) {
  if (cond) console.log(`  ok   ${name}`)
  else {
    console.log(`  FAIL ${name}${detail === undefined ? '' : ` — ${JSON.stringify(detail)}`}`)
    failures.push(name)
  }
}

function assertTokens(out) {
  const by = Object.fromEntries(out.tokens.list.map((t) => [t.name, t]))

  check('hex token resolves to canonical rgb',
    by['--brand'].kind === 'color' && by['--brand'].value === 'rgb(37, 99, 235)', by['--brand'])
  check('rem token resolves to px',
    by['--gap-4'].kind === 'length' && by['--gap-4'].value === '16px', by['--gap-4'])
  check('numeric weight token resolves as a weight',
    by['--weight-bold'].kind === 'weight' && by['--weight-bold'].value === '700', by['--weight-bold'])
  check('font stack token resolves as a family',
    by['--stack'].kind === 'family' && /Verdana/.test(by['--stack'].value), by['--stack'])
  check('shadow token resolves as a shadow',
    by['--shadow-sm'].kind === 'shadow' && by['--shadow-sm'].value.includes('rgba(0, 0, 0, 0.2)'), by['--shadow-sm'])

  // 1.5 is a legal font-weight, so a probe-order that tries weight before
  // recognising the shape types every line-height token as a weight, and the
  // px value an element computes can then never match it.
  check('unitless ratio token is typed as a ratio',
    by['--lh-normal'].kind === 'ratio' && by['--lh-normal'].value === 1.5, by['--lh-normal'])
  check('ratios are listed separately', out.tokens.ratios.includes(1.5), out.tokens.ratios)

  // #000 and 0px are what an unstyled probe reports; a guard that drops values
  // matching a baseline would discard --color-black and --radius-none, and every
  // black or square-cornered element would then read as off-token.
  check('a token equal to the property initial value still resolves',
    by['--pure-black'].kind === 'color' && by['--pure-black'].value === 'rgb(0, 0, 0)', by['--pure-black'])
  check('a zero-length token still resolves',
    by['--radius-none'].kind === 'length' && by['--radius-none'].value === '0px', by['--radius-none'])

  check('token pointing at an undefined variable is unresolved',
    by['--broken'].kind === 'unresolved', by['--broken'])
  check('token never declared anywhere is unresolved',
    by['--never-declared'].kind === 'unresolved', by['--never-declared'])
  check('resolved count matches', out.tokens.resolved === 9, out.tokens)

  // shadcn/ui stores colors as bare HSL channels and wraps them at the use site.
  // CSSOM rejects the bare form, so every token in such a project would read as
  // unresolved and the whole page would turn into off-token candidates.
  check('a bare HSL triplet resolves as a color',
    by['--shadcn'].kind === 'color' && by['--shadcn'].value === 'rgb(15, 23, 42)', by['--shadcn'])
}

function assertUsedAndOffToken(out) {
  check('used lists deduped colors', new Set(out.used.color).size === out.used.color.length, out.used.color)
  check('used lists deduped spacings', new Set(out.used.spacing).size === out.used.spacing.length, out.used.spacing)

  const offColors = (out.offToken.color || []).map((r) => r.value)
  const offSpacing = (out.offToken.spacing || []).map((r) => r.value)

  check('off-by-one color is flagged', offColors.includes('rgb(37, 99, 236)'), offColors)
  check('on-token color is not flagged', !offColors.includes('rgb(37, 99, 235)'), offColors)
  check('off-scale padding is flagged', offSpacing.includes('13px'), offSpacing)
  check('on-scale padding is not flagged', !offSpacing.includes('16px'), offSpacing)

  // A page-wide color written on body reaches every element by inheritance.
  check('hardcoded color on body is collected', out.used.color.includes('rgb(17, 17, 17)'), out.used.color)
  check('hardcoded font on body is collected',
    out.used.fontFamily.some((f) => /Georgia/.test(f)), out.used.fontFamily)

  // The px value an element computes for a ratio token can never equal the ratio.
  const offAll = Object.values(out.offToken).flat().map((r) => r.value)
  check('ratio values do not turn into off-token rows', !offAll.includes('1.5'), offAll)

  const row = (out.offToken.spacing || []).find((r) => r.value === '13px')
  check('off-token rows carry a count and samples',
    !!row && row.count > 0 && Array.isArray(row.sample) && row.sample.length > 0, row)

  // A bucket where nothing matched means the token set has no entry of that type;
  // listing every value in it gives a reviewer rows they cannot act on.
  check('buckets with no matching token are named rather than listed',
    Array.isArray(out.notCompared), out.notCompared)
}

function assertChecks(out) {
  // 25% black over white is rgb(191,191,191); measuring the declared color
  // instead reports a passing 21:1.
  const faint = out.checks.contrast.find((x) => x.sel.includes('faint'))
  check('semi-transparent text is composited before measuring',
    !!faint && faint.ratio > 1.5 && faint.ratio < 2.5, faint)

  // oklch is the default palette syntax in Tailwind v4; a regex parser drops it
  // and the element leaves no trace either way.
  const ok = out.checks.contrast.concat(out.checks.contrastUnknown).find((x) => x.sel.includes('oklch'))
  check('an oklch color is measured rather than skipped', !!ok && 'ratio' in ok, ok)

  const grad = out.checks.contrastUnknown.find((x) => x.sel.includes('ongrad'))
  check('text on a gradient is reported as unmeasurable', !!grad, out.checks.contrastUnknown)
  check('text on a gradient gets no made-up ratio',
    !out.checks.contrast.some((x) => x.sel.includes('ongrad')), out.checks.contrast)

  // WCAG 2.2 SC 2.5.8 is 24x24 at AA and exempts targets inside a sentence.
  // 44 is SC 2.5.5 at AAA, and using it floods the must-fix list with links
  // that do not violate anything.
  const targetSels = out.checks.targets.map((t) => t.sel)
  check('an undersized icon button is flagged', targetSels.some((s) => s.includes('icon')), out.checks.targets)
  check('a link inside a sentence is exempt',
    !out.checks.targets.some((x) => (x.sample || []).some((s) => s === 'a') && x.w > 40), out.checks.targets)

  const clip = out.checks.clipped.find((x) => x.sel.includes('wrap'))
  check('clipped overflow is flagged', !!clip && clip.scrollWidth === 400, clip)

  // An icon link computes to display:inline and sits in no sentence; keying the
  // WCAG Inline exception off display would drop exactly this case.
  check('an icon link is not treated as an inline exception',
    targetSels.some((s) => s === 'a'), out.checks.targets)

  // Repeated components should collapse into one row with a count.
  const t = out.checks.targets.find((x) => x.sel.includes('icon'))
  check('check rows carry a count', !!t && typeof t.count === 'number' && t.count >= 1, t)

  check('shadow roots are counted', out.unreachable.shadowRoots === 1, out.unreachable)
  check('frames are counted', out.unreachable.frames === 1, out.unreachable)
  check('viewport allows zooming', out.checks.viewportUserScalable === true, out.checks.viewportUserScalable)
  check('sampling is not truncated on a small fixture', out.truncated === false, out.sampled)
}

function assertScoped(scoped) {
  check('rootSelector limits sampling',
    scoped.used.spacing.includes('21px') && !scoped.used.color.includes('rgb(37, 99, 236)'), scoped.used)
}

function assertPayloadSize(out) {
  // The whole point of aggregating is that a reviewer can read the output.
  const bytes = JSON.stringify(out).length
  check(`payload stays small (${bytes} bytes)`, bytes < 8000, bytes)
}

async function main() {
  const pw = resolvePlaywright()
  if (!pw) {
    console.log('BLOCKED: playwright is not resolvable from this machine.')
    console.log('  inject-collect.js drives a real browser; without one these assertions cannot run.')
    return 2
  }

  const src = fs.readFileSync(INJECT, 'utf8')
  if (!src.includes('CONFIG')) {
    console.log('FAIL inject-collect.js no longer carries the CONFIG placeholder')
    return 1
  }

  const server = await serve(src)
  const base = `http://127.0.0.1:${server.address().port}/`

  let browser
  try {
    browser = await launch(pw)
    // The script is fetched with its placeholder intact and substituted in the
    // page: injecting it as a script tag would put the leading comment block on
    // the same line as an assignment and comment out the whole file.
    const run = (page, cfg) =>
      page.evaluate(async (c) => {
        const raw = await (await fetch('/inject.js')).text()
        return eval(raw.replace('CONFIG', JSON.stringify(c)))
      }, cfg)

    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    await page.goto(base, { waitUntil: 'load' })

    const out = await run(page, { tokens: TOKEN_NAMES })
    assertTokens(out)
    assertUsedAndOffToken(out)
    assertChecks(out)
    assertPayloadSize(out)
    assertScoped(await run(page, { tokens: TOKEN_NAMES, rootSelector: '#scoped' }))
  } finally {
    if (browser) await browser.close()
    server.close()
  }

  console.log()
  console.log(`browser: ${browserRevision}`)
  if (failures.length) {
    console.log(`${failures.length} failed: ${failures.join(', ')}`)
    return 1
  }
  console.log('browser checks all green')
  return 0
}

main().then((c) => process.exit(c)).catch((e) => {
  console.error(e)
  process.exit(1)
})

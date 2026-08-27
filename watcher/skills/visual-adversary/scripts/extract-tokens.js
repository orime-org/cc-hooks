#!/usr/bin/env node
// Collects design-token NAMES from a project's source. Values are resolved later
// in the browser, where the engine itself normalizes them — hex, hsl, rem and
// var() chains all come back as one canonical form, which hand-written
// conversion cannot match for correctness on edge cases.
//
// Usage: node extract-tokens.js <project-root> > tokens.json

const fs = require('fs')
const path = require('path')

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage', 'vendor'])

// Custom properties live wherever the project writes CSS. A Vue or Svelte SFC
// keeps them in a <style> block, styled-components and vanilla-extract keep them
// in a template literal inside a .ts file, and a static page keeps them in an
// inline <style>. Scanning only stylesheet extensions reports those projects as
// having no token definition at all, which switches off the whole first tier.
const STYLE_EXT = new Set([
  '.css', '.scss', '.sass', '.less', '.styl',
  '.vue', '.svelte', '.astro',
  '.ts', '.tsx', '.js', '.jsx', '.mjs',
  '.html', '.htm',
])
const MAX_FILES = 2000

const MAX_DEPTH = 12

// Both limits are recorded rather than applied silently: a truncated scan and a
// project with no tokens produce the same empty list, and the caller has to be
// able to tell them apart before reporting a missing token definition.
const limits = { depthHit: false, filesHit: false }

function walk(dir, out = [], depth = 0) {
  if (depth > MAX_DEPTH) {
    limits.depthHit = true
    return out
  }
  if (out.length >= MAX_FILES) {
    limits.filesHit = true
    return out
  }
  let entries
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const e of entries) {
    if (out.length >= MAX_FILES) {
      limits.filesHit = true
      break
    }
    const full = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name) || e.name.startsWith('.')) continue
      walk(full, out, depth + 1)
    } else if (STYLE_EXT.has(path.extname(e.name))) {
      out.push(full)
    }
  }
  return out
}

// Matches `--token-name:` at a declaration position. The value is deliberately
// not captured — see the header note.
const DECL = /(^|[;{\s])(--[A-Za-z0-9_-]+)\s*:/g

function collectNames(files, root) {
  const names = new Map() // name -> Set of relative file paths

  for (const file of files) {
    let text
    try {
      text = fs.readFileSync(file, 'utf8')
    } catch {
      continue
    }
    const rel = path.relative(root, file)
    let m
    while ((m = DECL.exec(text)) !== null) {
      const name = m[2]
      if (!names.has(name)) names.set(name, new Set())
      names.get(name).add(rel)
    }
  }

  return names
}

function detectTailwind(root) {
  const candidates = ['tailwind.config.js', 'tailwind.config.ts', 'tailwind.config.cjs', 'tailwind.config.mjs']
  const found = candidates.filter((c) => fs.existsSync(path.join(root, c)))
  return found.length ? found : null
}

function main() {
  const root = path.resolve(process.argv[2] || '.')

  if (!fs.existsSync(root)) {
    console.error(`project root not found: ${root}`)
    process.exit(2)
  }

  const files = walk(root)
  const names = collectNames(files, root)
  const tailwind = detectTailwind(root)

  const tokens = [...names.entries()]
    .map(([name, srcSet]) => ({ name, sources: [...srcSet].sort() }))
    .sort((a, b) => a.name.localeCompare(b.name))

  const truncated = limits.filesHit || limits.depthHit

  const result = {
    root,
    scannedFiles: files.length,
    truncated,
    truncatedBy: truncated ? { files: limits.filesHit, depth: limits.depthHit } : null,
    tokenCount: tokens.length,
    tokens,
    tailwindConfig: tailwind,
    // A Tailwind project keeps its scale in the config object, not in CSS
    // variables. Reading it needs the project's own module resolution, so the
    // skill asks for it rather than guessing from rendered output — inferring a
    // baseline from what shipped would pass an implementation that never used
    // the scale at all.
    note: tailwind
      ? 'Tailwind config detected. Supply the theme scale separately; CSS variables below may be partial.'
      : tokens.length
        ? null
        : truncated
          ? 'Scan hit a limit before finding any custom property. Re-run on a narrower root before concluding anything.'
          : 'No CSS custom properties found. Report the project as lacking a token definition.',
  }

  process.stdout.write(JSON.stringify(result, null, 2) + '\n')
}

main()

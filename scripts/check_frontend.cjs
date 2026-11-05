// Read npm's lock format with Node: Windows PowerShell 5.1 cannot parse its empty root key.
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..', 'frontend')
const read = (name) => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'))
const stable = (value = {}) => JSON.stringify(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)))
try {
  const declared = read('package.json')
  const lock = read('package-lock.json')
  for (const key of ['dependencies', 'devDependencies']) {
    if (stable(declared[key]) !== stable(lock.packages[''][key])) {
      console.log(JSON.stringify({ ok: false, declarationMismatch: true }))
      process.exit(0)
    }
  }
  const installed = read('node_modules/.package-lock.json')
  let valid = true
  for (const [name, item] of Object.entries(installed.packages)) {
    const expected = lock.packages[name]
    if (!expected || ['version', 'resolved', 'integrity'].some((key) => item[key] !== expected[key])) valid = false
  }
  for (const [name, item] of Object.entries(lock.packages)) {
    if (!name || item.optional || item.devOptional || item.link) continue
    if (item.os && !item.os.includes(process.platform)) continue
    if (item.cpu && !item.cpu.includes(process.arch)) continue
    const actual = read(`${name}/package.json`)
    if (actual.version !== item.version) valid = false
  }
  console.log(JSON.stringify({ ok: valid, declarationMismatch: false }))
} catch {
  console.log(JSON.stringify({ ok: false, declarationMismatch: false }))
}

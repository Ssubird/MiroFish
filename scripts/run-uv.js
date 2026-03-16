const { spawnSync } = require('child_process')
const { existsSync } = require('fs')
const { homedir } = require('os')
const { join } = require('path')

const args = process.argv.slice(2)

if (!args.length) {
  console.error('Usage: node scripts/run-uv.js <uv-args...>')
  process.exit(1)
}

const candidates = [
  'uv',
  join(homedir(), '.local', 'bin', process.platform === 'win32' ? 'uv.exe' : 'uv'),
]

let lastError = null

for (const candidate of candidates) {
  if (candidate !== 'uv' && !existsSync(candidate)) {
    continue
  }

  const result = spawnSync(candidate, args, {
    stdio: 'inherit',
    shell: false,
  })

  if (!result.error) {
    process.exit(result.status ?? 0)
  }

  lastError = result.error
  if (result.error.code !== 'ENOENT') {
    break
  }
}

console.error('Unable to find uv. Expected it in PATH or in ~/.local/bin/uv(.exe).')
if (lastError) {
  console.error(lastError.message)
}
process.exit(1)

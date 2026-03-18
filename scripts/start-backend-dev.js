const http = require('http')
const { execFileSync, spawn } = require('child_process')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const BACKEND_ROOT = path.join(ROOT, 'backend')
const PORT = Number(process.env.FLASK_PORT || 5001)
const HEALTH_PATH = '/health'
const HEALTH_TIMEOUT_MS = 1200
const PORT_FREE_RETRIES = 20
const PORT_FREE_DELAY_MS = 500
const SKIP_CLEANUP = String(process.env.MIROFISH_SKIP_BACKEND_PORT_CLEANUP || '').trim().toLowerCase() === 'true'
const PYTHON_ARGS = ['../scripts/run-uv.js', 'run', 'python', 'run.py']

async function main() {
  if (!SKIP_CLEANUP) {
    await ensureBackendPortReady()
  } else {
    console.log(`[backend] Skip port cleanup because MIROFISH_SKIP_BACKEND_PORT_CLEANUP=true`)
  }
  runBackend()
}

async function ensureBackendPortReady() {
  const health = await probeHealth()
  const pid = getListeningPid(PORT)
  if (!pid) {
    return
  }
  if (health.ok && health.payload && health.payload.service === 'MiroFish Backend') {
    console.log(`[backend] Found existing MiroFish backend on port ${PORT} (pid ${pid}), stopping it before restart.`)
    killProcessTree(pid)
    await waitForPortFree(PORT)
    return
  }
  const detail = health.error
    ? `health probe failed: ${health.error}`
    : `unexpected /health response: ${JSON.stringify(health.payload)}`
  throw new Error(
    `Port ${PORT} is already in use by pid ${pid}. ${detail}. ` +
    `Refusing to kill it automatically because it does not look like the MiroFish backend.`,
  )
}

function probeHealth() {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: '127.0.0.1',
        port: PORT,
        path: HEALTH_PATH,
        timeout: HEALTH_TIMEOUT_MS,
      },
      (res) => {
        let body = ''
        res.setEncoding('utf8')
        res.on('data', (chunk) => {
          body += chunk
        })
        res.on('end', () => {
          try {
            resolve({ ok: res.statusCode === 200, payload: JSON.parse(body), error: null })
          } catch (error) {
            resolve({ ok: false, payload: null, error: error.message })
          }
        })
      },
    )
    req.on('timeout', () => {
      req.destroy(new Error('timeout'))
    })
    req.on('error', (error) => {
      resolve({ ok: false, payload: null, error: error.message })
    })
  })
}

function getListeningPid(port) {
  if (process.platform === 'win32') {
    const output = execCommand('powershell', ['-NoProfile', '-Command', buildWindowsPortQuery(port)])
    const pid = Number.parseInt(output.trim(), 10)
    return Number.isFinite(pid) ? pid : null
  }
  const output = execCommand('bash', ['-lc', `lsof -ti tcp:${port} -sTCP:LISTEN 2>/dev/null | head -n 1`])
  const pid = Number.parseInt(output.trim(), 10)
  return Number.isFinite(pid) ? pid : null
}

function buildWindowsPortQuery(port) {
  return [
    '$conn = $null',
    `try { $conn = Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction Stop | Select-Object -First 1 } catch {}`,
    'if ($conn) { Write-Output $conn.OwningProcess }',
    'exit 0',
  ].join('; ')
}

function killProcessTree(pid) {
  if (process.platform === 'win32') {
    execCommand('taskkill', ['/PID', String(pid), '/T', '/F'])
    return
  }
  process.kill(pid, 'SIGTERM')
}

async function waitForPortFree(port) {
  for (let attempt = 0; attempt < PORT_FREE_RETRIES; attempt += 1) {
    if (!getListeningPid(port)) {
      return
    }
    await sleep(PORT_FREE_DELAY_MS)
  }
  throw new Error(`Port ${port} is still busy after stopping the previous backend.`)
}

function runBackend() {
  const child = spawn(process.execPath, PYTHON_ARGS, {
    cwd: BACKEND_ROOT,
    stdio: 'inherit',
    shell: false,
    env: process.env,
  })

  const forwardSignal = (signal) => {
    if (!child.killed) {
      child.kill(signal)
    }
  }

  process.on('SIGINT', forwardSignal)
  process.on('SIGTERM', forwardSignal)

  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })
}

function execCommand(command, args) {
  return execFileSync(command, args, {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

main().catch((error) => {
  console.error(`[backend] ${error.message}`)
  process.exit(1)
})

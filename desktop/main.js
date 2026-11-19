const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

const PORT = process.env.V2D_PORT || 8000
let backend = null

function reachable() {
  return new Promise(resolve => {
    const req = http.get(`http://127.0.0.1:${PORT}/api/health`, res => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(1500, () => { req.destroy(); resolve(false) })
  })
}

async function ensureBackend() {
  if (await reachable()) return
  const isPackaged = app.isPackaged
  const cwd = isPackaged
    ? path.join(process.resourcesPath, 'backend')
    : path.join(__dirname, '..', 'backend')
  const python = process.platform === 'win32' ? 'python' : 'python3'
  backend = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(PORT)], {
    cwd,
    env: { ...process.env, OWNER_EMAILS: process.env.OWNER_EMAILS || 'owner@example.com' },
    stdio: 'ignore',
  })
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 500))
    if (await reachable()) return
  }
  dialog.showErrorBox('Backend failed to start', `Check that Python and the backend dependencies are installed in ${cwd}`)
}

async function createWindow() {
  await ensureBackend()
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 940,
    title: 'Video to 3D Studio',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  })
  win.loadURL(`http://127.0.0.1:${PORT}`)
}

app.whenReady().then(createWindow)
app.on('window-all-closed', () => {
  if (backend) backend.kill()
  if (process.platform !== 'darwin') app.quit()
})
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })

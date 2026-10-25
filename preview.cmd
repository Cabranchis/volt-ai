@echo off
rem Live preview of the web app: edits show up in the browser as you save them.
cd /d "%~dp0web"
start "" http://localhost:3000/es
npm run preview

#!/usr/bin/env node
// claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
// Free to use. Modifying, copying or redistributing this code is not permitted.
// License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
//
// Lancador npm: baixa o ClaudeTray.exe oficial do GitHub Releases na primeira
// execucao, confere o SHA-256 gravado em release.json e so entao executa.
// Sem postinstall de proposito: nada roda na maquina do usuario no `npm i`,
// so quando ele chama o comando.
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const https = require("https");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const release = require("../release.json");

if (process.platform !== "win32") {
  console.error("claude-tray runs on Windows only.");
  process.exit(1);
}

const pasta = path.join(os.homedir(), ".claude-tray", "bin");
const exe = path.join(pasta, `ClaudeTray-${release.version}.exe`);

function baixar(url, destino, saltos = 5) {
  return new Promise((ok, falha) => {
    https.get(url, { headers: { "User-Agent": "svatka-claude-tray" } }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && saltos > 0) {
        res.resume();
        return ok(baixar(res.headers.location, destino, saltos - 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return falha(new Error(`download failed: HTTP ${res.statusCode}`));
      }
      const arquivo = fs.createWriteStream(destino);
      res.pipe(arquivo);
      arquivo.on("finish", () => arquivo.close(ok));
      arquivo.on("error", falha);
    }).on("error", falha);
  });
}

function sha256(arquivo) {
  return crypto.createHash("sha256").update(fs.readFileSync(arquivo)).digest("hex");
}

async function garantirExe() {
  if (fs.existsSync(exe) && sha256(exe) === release.sha256) return;
  fs.mkdirSync(pasta, { recursive: true });
  const temporario = `${exe}.part`;
  console.error(`Downloading Claude Tray ${release.version} (Svatka Technologies™)...`);
  await baixar(release.url, temporario);
  // Hash errado = binario que nao e o oficial. Apaga e recusa, nunca executa.
  if (sha256(temporario) !== release.sha256) {
    fs.rmSync(temporario, { force: true });
    throw new Error("checksum mismatch: the downloaded file is not the official build.");
  }
  fs.renameSync(temporario, exe);
}

(async () => {
  try {
    await garantirExe();
  } catch (erro) {
    console.error(`claude-tray: ${erro.message}`);
    process.exit(1);
  }

  const args = process.argv.slice(2);
  if (args.length === 0) {
    // Sem argumentos: sobe a bandeja solta e devolve o terminal.
    spawn(exe, [], { detached: true, stdio: "ignore" }).unref();
    console.log("Claude Tray is running in the system tray.");
    return;
  }
  // --status, --autostart, --config...: espera e repassa a saida.
  const filho = spawn(exe, args, { stdio: "inherit" });
  filho.on("exit", (codigo) => process.exit(codigo ?? 0));
})();

// Tiny JSON-file persistence for the dev instance. The registry, keys and
// ledger map live in the state dir (outside the repo). Task events append
// to a JSONL log so the ledger can be rebuilt/audited.
import fs from "node:fs";
import path from "node:path";

export class StateStore {
  constructor(dir) {
    this.dir = dir;
    fs.mkdirSync(dir, { recursive: true });
  }

  _file(name) {
    return path.join(this.dir, name);
  }

  readJson(name, fallback) {
    try {
      return JSON.parse(fs.readFileSync(this._file(name), "utf8"));
    } catch {
      return fallback;
    }
  }

  writeJson(name, value, mode) {
    const tmp = this._file(name + ".tmp");
    fs.writeFileSync(tmp, JSON.stringify(value, null, 2), mode ? { mode } : undefined);
    fs.renameSync(tmp, this._file(name));
  }

  appendJsonl(name, obj) {
    fs.appendFileSync(this._file(name), JSON.stringify(obj) + "\n");
  }

  readText(name) {
    try {
      return fs.readFileSync(this._file(name), "utf8");
    } catch {
      return null;
    }
  }

  writeText(name, text, mode = 0o600) {
    fs.writeFileSync(this._file(name), text, { mode });
  }

  exists(name) {
    return fs.existsSync(this._file(name));
  }
}

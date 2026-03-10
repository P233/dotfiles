const { execFile } = require("child_process");
const path = require("path");
const os = require("os");
const vscode = require("vscode");

const EMACSCLIENT = "/opt/homebrew/bin/emacsclient";
const SOCKET = path.join(os.homedir(), ".config", "emacs", "server", "server");

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("open-in-emacs.open", () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;

      const file = editor.document.fileName;
      const line = editor.selection.active.line + 1;

      execFile(
        EMACSCLIENT,
        ["-s", SOCKET, "--no-wait", `+${line}`, file],
        (err) => {
          if (err) {
            // Server not running — launch Emacs.app with the file via `open`
            execFile("open", ["-a", "Emacs", "--args", `+${line}`, file]);
            return;
          }
          execFile("open", ["-a", "Emacs"]);
        }
      );
    })
  );
}

module.exports = { activate };

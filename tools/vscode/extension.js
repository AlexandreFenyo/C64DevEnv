// Extension VS Code du dépôt C64DevEnv : type de débogage "c64".
// L'adaptateur est tools/dap.py du dossier ouvert (Python, bibliothèque
// standard) : l'extension ne fait que le lancer, tout le reste est dans le dépôt.
'use strict';
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

function adapterOf(folder) {
  return path.join(folder, 'tools', 'dap.py');
}

function findRoot(session) {
  const candidates = [];
  if (session.workspaceFolder) candidates.push(session.workspaceFolder.uri.fsPath);
  for (const f of vscode.workspace.workspaceFolders || []) candidates.push(f.uri.fsPath);
  return candidates.find((f) => fs.existsSync(adapterOf(f)));
}

function activate(context) {
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory('c64', {
    createDebugAdapterDescriptor(session) {
      const root = findRoot(session);
      if (!root) {
        throw new Error('tools/dap.py introuvable : ouvrez le dossier C64DevEnv dans VS Code (WSL).');
      }
      const python = session.configuration.python || 'python3';
      return new vscode.DebugAdapterExecutable(python, [adapterOf(root)], { cwd: root });
    },
  }));
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider('c64', {
    // F5 sans launch.json : programme du fichier courant, arrêt au début.
    resolveDebugConfiguration(folder, config) {
      if (!config.type && !config.request && !config.name) {
        const editor = vscode.window.activeTextEditor;
        if (!editor || !['ca65', 'c'].includes(editor.document.languageId)) {
          return config;
        }
        config.type = 'c64';
        config.request = 'launch';
        config.name = 'C64 : fichier courant';
        config.stopOnEntry = true;
      }
      if (config.request === 'launch' && !config.program) {
        config.program = '${file}';
      }
      return config;
    },
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };

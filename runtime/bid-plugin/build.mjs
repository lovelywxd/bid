import { resolve } from 'node:path';
import { mkdir, readFile, writeFile, symlink } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const source = resolve('../builds/harness-e8f7b93/deepseek-harness-e8f7b93a344964de3dca1ace9e72b6e4d6de87cb');
const { default: ts } = await import(pathToFileURL(resolve(source, 'node_modules/typescript/lib/typescript.js')).href);
await mkdir('dist', { recursive: true });
const output = ts.transpileModule(await readFile('src/index.ts', 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2024, module: ts.ModuleKind.ESNext, strict: true },
});
await writeFile('dist/index.mjs', output.outputText);
try { await symlink(resolve(source, 'node_modules'), 'node_modules', 'dir'); }
catch (error) { if (error.code !== 'EEXIST') throw error; }

import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';
const source = resolve('../builds/harness-e8f7b93/deepseek-harness-e8f7b93a344964de3dca1ace9e72b6e4d6de87cb');
const { default: ts } = await import(pathToFileURL(resolve(source, 'node_modules/typescript/lib/typescript.js')).href);
const config = ts.readConfigFile(resolve(source, 'tsconfig.base.json'), ts.sys.readFile);
// Consume the official build's public declarations without flattening its
// distinct host/vendor ts.Programs into a new, incompatible source program.
const paths = Object.fromEntries(Object.entries(config.config.compilerOptions.paths).map(([name, values]) => [
  name, values.map(value => {
    const candidate = resolve(source, value.replace('/src', '/lib/types').replace(/\.tsx?$/, '.d.ts'));
    return existsSync(candidate) || candidate.includes('*') ? candidate
      : existsSync(`${candidate}/index.d.ts`) ? `${candidate}/index.d.ts` : resolve(source, value);
  }),
]));
const parsed = ts.parseJsonConfigFileContent({...config.config, compilerOptions: {
  ...config.config.compilerOptions, noEmit: true, composite: false, incremental: false,
  skipLibCheck: true, strict: true, rootDir: undefined, paths,
}, files: [resolve('src/index.ts')], include: [], exclude: []}, ts.sys, source);
const program = ts.createProgram(parsed.fileNames, parsed.options);
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
if (diagnostics.length) {
  process.stderr.write(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: x => x, getCurrentDirectory: () => source, getNewLine: () => '\n',
  }));
  process.exit(1);
}
console.log('Bid plugin strict typecheck passed.');

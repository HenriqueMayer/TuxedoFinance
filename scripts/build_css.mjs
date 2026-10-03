// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// One-off builds use PostCSS without the CLI's file-watching dependency chain.
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import postcss from 'postcss';
import tailwindcss from '@tailwindcss/postcss';

const root = fileURLToPath(new URL('../', import.meta.url));
const input = resolve(root, 'assets/css/tailwind.css');
const output = resolve(root, process.argv[2] || 'static/css/app.css');
const result = await postcss([tailwindcss({base: root, optimize: {minify: true}})])
    .process(await readFile(input, 'utf8'), {from: input, to: output, map: false});
await writeFile(output, result.css);
console.log(`Compiled CSS: ${output}`);

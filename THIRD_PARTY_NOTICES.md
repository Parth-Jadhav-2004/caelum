# Third-party notices

## T3 Code color palettes

`src/lib/t3-themes.generated.css` adapts the built-in color values from
[`packages/shared/src/themePalettes.ts`](https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packages/shared/src/themePalettes.ts),
commit `f313d0a6cb843551fb60e57a454a71e71a3a8c04` (inspected November 13, 2026).
The mapping uses Caelum’s shadcn semantic tokens. No T3 logos or sidebar artwork
are included. T3 Tools does not endorse Caelum.

To deliberately refresh the pinned snapshot, review an upstream checkout, run
`node scripts/import-t3-themes.mjs /path/to/t3code`, review the diff, update this
notice, and run the theme checks. The importer reads literals through TypeScript’s
parser and does not execute upstream code.

MIT License

Copyright (c) 2026 T3 Tools Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

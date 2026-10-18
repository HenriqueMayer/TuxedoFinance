// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {resolve} = require('node:path');

// Resolve from this stable helper directory, independently of spec grouping.
const projectRoot = resolve(__dirname, '../../..');

module.exports = {projectRoot};

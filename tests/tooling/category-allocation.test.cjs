// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {cents, decimal, distribute} = require('../../static/js/category-allocation.js');
const auto = () => ({fixed: false, amount: null});
const fixed = value => ({fixed: true, amount: cents(value)});

test('three automatic categories retain every cent and deterministically assign remainders', () => {
    assert.deepEqual(distribute(cents('100.00'), [auto(), auto(), auto()]).amounts, [3334n, 3333n, 3333n]);
    assert.deepEqual(distribute(cents('100.01'), [auto(), auto(), auto()]).amounts, [3334n, 3334n, 3333n]);
});
test('edited amounts remain fixed while only automatic categories receive the remainder', () => {
    const result = distribute(cents('100.01'), [fixed('10.00'), auto(), auto()]);
    assert.deepEqual(result.amounts, [1000n, 4501n, 4500n]);
    assert.equal(distribute(cents('100.01'), [fixed('10.00'), auto()]).remainderIndex, 1);
});
test('adding, removing and changing the total retain manual allocations', () => {
    assert.deepEqual(distribute(cents('120.01'), [fixed('20.00'), auto(), auto(), auto()]).amounts,
        [2000n, 3334n, 3334n, 3333n]);
    assert.deepEqual(distribute(cents('90.01'), [fixed('20.00'), auto()]).amounts, [2000n, 7001n]);
});
test('an excessive edit returns its precise cap without truncating any input', () => {
    const rows = [fixed('70.00'), fixed('40.00'), auto()];
    const result = distribute(cents('100.00'), rows);
    assert.equal(result.error, 'limit');
    assert.deepEqual(result.limits, [5999n, 2999n, null]);
    assert.deepEqual(rows, [fixed('70.00'), fixed('40.00'), auto()]);
});
test('zero, invalid precision, too few cents and incomplete fixed splits remain recoverable errors', () => {
    assert.equal(cents('12.345'), null);
    assert.equal(cents('-1'), null);
    assert.equal(cents('invalid'), null);
    assert.equal(distribute(cents('0.01'), [auto(), auto()]).error, 'small');
    assert.equal(distribute(cents('100'), [fixed('0'), auto()]).error, 'amount');
    assert.equal(distribute(cents('100'), [fixed('20'), fixed('30')]).error, 'sum');
    assert.equal(distribute(cents('100'), [auto()]).error, 'count');
});
test('the model monetary range stays exact beyond Number.MAX_SAFE_INTEGER', () => {
    const total = cents('99999999999999.99');
    const result = distribute(total, [auto(), auto(), auto()]);
    assert.equal(result.amounts.reduce((sum, value) => sum + value, 0n), total);
    assert.equal(decimal(total), '99999999999999.99');
});

const test = require('node:test');
const assert = require('node:assert/strict');
const { escapeHtml, moneyText, intText } = require('../dist/core.js');

test('unknown money stays null, not zero', () => {
  assert.equal(moneyText('', true), null);
  assert.equal(moneyText(null, true), null);
  assert.throws(() => moneyText(''));
  assert.equal(moneyText('0', true), '0.00');
});
test('amount input preserves cents without floating-point multiplication', () => {
  assert.equal(moneyText('00012.3'), '12.30');
  assert.equal(moneyText('0.01'), '0.01');
  assert.equal(moneyText('1000000000000'), '1000000000000.00');
});
test('rejects negative, nonfinite, exponent, commas and overprecision', () => {
  for (const value of ['-1', 'NaN', 'Infinity', '1e3', '1,000', '1.001', '1000000000000.01', '1000000000001']) {
    assert.throws(() => moneyText(value), value);
  }
});
test('quantities cannot silently become zero, fractional or unsafe', () => {
  for (const value of ['', '1.5', '-1', 'NaN', '9007199254740993']) assert.throws(() => intText(value), value);
  assert.equal(intText('0'), 0);
  assert.equal(intText('12'), 12);
});
test('merchant and evidence text is escaped in element and attribute contexts', () => {
  assert.equal(escapeHtml('<script>"&\'</script>'), '&lt;script&gt;&quot;&amp;&#39;&lt;/script&gt;');
  assert.equal(escapeHtml(null), '');
});

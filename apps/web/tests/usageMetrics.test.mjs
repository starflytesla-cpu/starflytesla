import assert from 'node:assert/strict'
import { test } from 'node:test'
import { failureRate, formatUsd, highFailure } from '../src/api/usageMetrics.ts'

test('未知價格、真實零與小額支出維持不同含義', () => {
  assert.equal(formatUsd(null), '未設定價格')
  assert.equal(formatUsd(undefined), '未設定價格')
  assert.equal(formatUsd(0), '$0.00')
  assert.equal(formatUsd(0.000023), '<$0.0001')
  assert.equal(formatUsd(0.0001), '$0.0001')
  assert.equal(formatUsd(0.00234), '$0.0023')
  assert.equal(formatUsd(0.01), '$0.01')
  assert.equal(formatUsd(1234.567), '$1234.57')
})
test('失敗占比以全部呼叫為分母；沒有呼叫時不產生比例', () => {
  assert.equal(failureRate(0, 0), null)
  assert.equal(failureRate(100, 38), 38)
  assert.ok(Math.abs(failureRate(101, 38) - 37.6237623762) < 0.000001)
})
test('高失敗提示需要足夠樣本，避免一筆失敗誤報', () => {
  assert.equal(highFailure(1, 1), false)
  assert.equal(highFailure(19, 19), false)
  assert.equal(highFailure(20, 3), false)
  assert.equal(highFailure(20, 4), true)
  assert.equal(highFailure(0, 0), false)
})

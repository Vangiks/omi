/**
 * STATIC CHECKER (not behavioral coverage) for the create-app form.
 * Run: npm test  (from web/frontend)
 *
 * Billing is removed from the fork and the backend no longer serves
 * /v1/app/plans. The form used to offer "Paid" and gate submission on a
 * payment plan that could never load, so a developer who picked it could not
 * submit. page.tsx and the server actions cannot be imported by node:test,
 * so the checks read their source.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const page = read('../app/create-app/page.tsx');
const initData = read('../actions/apps/get-app-initialization-data.ts');
const submitApp = read('../actions/apps/submit-app.ts');

const PAYMENT_FIELDS = /\b(paymentPlans|PaymentPlan|isPaid|setIsPaid|selectedPaymentPlan|is_paid|payment_plan|price|setPrice)\b/;

describe('create-app without paid apps (static checker)', () => {
  it('page has no payment state, switch or request fields', () => {
    assert.doesNotMatch(page, PAYMENT_FIELDS);
  });

  it('initialization data does not request /v1/app/plans', () => {
    assert.doesNotMatch(initData, /app\/plans/);
    assert.doesNotMatch(initData, PAYMENT_FIELDS);
  });

  it('submission payload type has no payment fields', () => {
    assert.doesNotMatch(submitApp, PAYMENT_FIELDS);
  });
});

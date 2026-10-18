// Backend REST schema authority lives in ./omiApi.generated.ts, generated from
// docs/api-reference/app-client-openapi.json. This file re-exports those
// generated types under the names admin consumers import, plus behavior-only
// adapters (request-body builders, client-narrowed unions) that are not backend
// schema.

import type { App } from './omiApi.generated';

/**
 * `OmiApp` is the legacy alias for the generated `App` schema — the backend
 * REST authority for `/v1/apps`. The hand-written mirror is retired in favor
 * of the generated DTO.
 */
export type OmiApp = App;

/**
 * App capability. The backend `App.capabilities` is typed as `Array<string>`;
 * this union narrows to the known values the admin UI renders, while still
 * accepting other strings the API may return.
 */
export type OmiAppCapability =
  | 'memories'
  | 'chat'
  | 'proactive_notification'
  | 'external_integration'
  | 'persona'
  | (string & {});

/**
 * App status. The backend `App.status` is typed as `string`; this union
 * narrows to the known values the admin UI renders.
 */
export type OmiAppStatus = 'approved' | 'pending' | 'rejected' | 'under-review' | (string & {});

/**
 * App payment plan. The backend `App.payment_plan` is typed as `string`;
 * this union narrows to the known values the admin UI renders.
 */
export type OmiPaymentPlan = 'free' | 'one-time' | 'monthly' | 'yearly' | (string & {});

/**
 * Request-body builder for create/update app. Client-side shape derived from
 * the generated `App` response schema; the backend accepts a subset of fields.
 */
export type OmiAppInput = Partial<
  Omit<
    OmiApp,
    | 'id'
    | 'uid'
    | 'approved'
    | 'status'
    | 'reviews'
    | 'user_review'
    | 'rating_avg'
    | 'rating_count'
    | 'deleted'
    | 'installs'
    | 'created_at'
    | 'payment_product_id'
    | 'payment_price_id'
    | 'payment_link_id'
    | 'payment_link'
    | 'is_user_paid'
    | 'thumbnail_urls'
    | 'is_popular'
    | 'is_influencer'
  >
>;

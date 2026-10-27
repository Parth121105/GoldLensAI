// One short line per verdict, always shown next to the label. The full explanations
// (lib/labels.ts VERDICTS[...].explain) stay behind Details.

import type { Verdict } from '../../../api/types'

export const VERDICT_SHORT: Record<Verdict, string> = {
  insufficient_data: 'Too few signals to test; no result is reported.',
  not_supported: 'Flagged moves did not reliably revert out of sample.',
  supported_before_costs_costs_unknown: 'Reverted out of sample, but costs are unknown.',
  not_supported_after_costs: 'Reversion was smaller than round-trip costs.',
  historically_validated: 'Survived out-of-sample testing net of costs; historical only.',
}

export const SAMPLE_QUEUE_FILTERS = [
  { key: "ready_for_review", label: "Ready for QA review" },
  { key: "blocked_incomplete", label: "Blocked / incomplete" },
  { key: "oos_investigation", label: "OOS / investigation" },
  { key: "instrument_issue", label: "Instrument issue" },
  { key: "approved", label: "Approved" },
  { key: "returned_rejected", label: "Returned / rejected" },
];

export function sampleQueueRows(payload, key) {
  return payload?.sample_queues?.[key] || [];
}

export function sampleQueueCount(payload, key) {
  return payload?.sample_queue_counts?.[key] || 0;
}

export function totalSampleAttentionRecords(payload) {
  const ids = new Set();
  SAMPLE_QUEUE_FILTERS.forEach(({ key }) => {
    sampleQueueRows(payload, key).forEach((record) => ids.add(record.id));
  });
  return ids.size;
}
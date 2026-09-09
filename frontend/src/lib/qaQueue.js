export const SAMPLE_QUEUE_FILTERS = [
  { key: "ready", label: "Ready for QA review" },
  { key: "blocked", label: "Blocked / incomplete" },
  { key: "oos", label: "OOS / investigation" },
  { key: "instrument_issue", label: "Instrument issue" },
  { key: "approved", label: "Approved" },
  { key: "returned", label: "Returned / rejected" },
];

export function queueRequestParams(category, page, pageSize, search) {
  return {
    category,
    page,
    page_size: pageSize,
    ...(search.trim() ? { search: search.trim() } : {}),
  };
}

export function sampleQueueCount(payload, key) {
  return payload?.category_counts?.[key] || 0;
}

export function totalSampleAttentionRecords(payload) {
  return payload?.total_attention_records || 0;
}

export function paginationLabel(payload) {
  return `Page ${payload?.page || 1} of ${payload?.total_pages || 1}`;
}

export function isLatestQueueResponse(requestId, latestRequestId) {
  return requestId === latestRequestId;
}
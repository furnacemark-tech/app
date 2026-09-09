import {
  sampleQueueCount,
  sampleQueueRows,
  totalSampleAttentionRecords,
} from "./qaQueue";

describe("QA queue display helpers", () => {
  const payload = {
    sample_queues: {
      ready_for_review: [{ id: "one", record_id: "REC-1" }],
      blocked_incomplete: [{ id: "two", record_id: "REC-2" }],
      instrument_issue: [{ id: "two", record_id: "REC-2" }],
    },
    sample_queue_counts: {
      ready_for_review: 1,
      blocked_incomplete: 1,
      instrument_issue: 1,
    },
  };

  it("uses backend-provided category rows and counts", () => {
    expect(sampleQueueRows(payload, "ready_for_review")).toEqual([
      { id: "one", record_id: "REC-1" },
    ]);
    expect(sampleQueueCount(payload, "instrument_issue")).toBe(1);
  });

  it("counts distinct records once when they have multiple attention reasons", () => {
    expect(totalSampleAttentionRecords(payload)).toBe(2);
  });

  it("provides an empty array for a classification with no records", () => {
    expect(sampleQueueRows(payload, "approved")).toEqual([]);
  });
});
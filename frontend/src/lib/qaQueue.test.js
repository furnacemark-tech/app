import {
  isLatestQueueResponse,
  paginationLabel,
  queueRequestParams,
  sampleQueueCount,
  totalSampleAttentionRecords,
} from "./qaQueue";

describe("QA queue display helpers", () => {
  const payload = {
    category_counts: {
      ready: 1,
      blocked: 1,
      instrument_issue: 1,
    },
    total_attention_records: 2,
    page: 2,
    total_pages: 4,
  };

  it("builds the initial category request", () => {
    expect(queueRequestParams("ready", 1, 25, "")).toEqual({
      category: "ready",
      page: 1,
      page_size: 25,
    });
  });

  it("sends trimmed search and resets are controlled by caller page state", () => {
    expect(queueRequestParams("oos", 1, 25, " REC-0201 ")).toEqual({
      category: "oos",
      page: 1,
      page_size: 25,
      search: "REC-0201",
    });
  });

  it("uses backend-provided category counts and pagination text", () => {
    expect(sampleQueueCount(payload, "ready")).toBe(1);
    expect(sampleQueueCount(payload, "instrument_issue")).toBe(1);
    expect(paginationLabel(payload)).toBe("Page 2 of 4");
  });

  it("counts distinct records once when they have multiple attention reasons", () => {
    expect(totalSampleAttentionRecords(payload)).toBe(2);
  });

  it("accepts only the latest response when requests complete out of order", () => {
    expect(isLatestQueueResponse(4, 4)).toBe(true);
    expect(isLatestQueueResponse(3, 4)).toBe(false);
  });
});
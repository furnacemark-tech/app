import { coaEligibility, coaErrorMessage } from "../lib/coaEligibility";

describe("sample CoA eligibility", () => {
  const approvedSample = { qa_status: "Approved" };

  it("blocks ordinary CoA while required results are outstanding", () => {
    expect(coaEligibility(approvedSample, true, ["COD", "Ammonia"])).toEqual({
      eligible: false,
      message: "CoA is unavailable until required results are entered: COD, Ammonia.",
    });
  });

  it("blocks CoA until the complete record has QA approval", () => {
    expect(coaEligibility({ qa_status: "Pending Review" }, false, [])).toEqual({
      eligible: false,
      message: "CoA is unavailable until QA approves this complete record.",
    });
  });

  it("allows CoA for a complete QA-approved record", () => {
    expect(coaEligibility(approvedSample, false, [])).toEqual({
      eligible: true,
      message: "",
    });
  });

  it("blocks CoA when required instrument traceability is invalid", () => {
    expect(
      coaEligibility(approvedSample, false, [], [
        { parameter: "Methanol", reason: "A registered GC instrument is required." },
      ]),
    ).toEqual({
      eligible: false,
      message:
        "CoA is unavailable until instrument traceability is corrected. " +
        "Methanol: A registered GC instrument is required.",
    });
  });

  it("formats an unexpected 422 response for a controlled toast", () => {
    expect(
      coaErrorMessage({
        message: "Cannot issue an ordinary CoA: required results are missing",
        outstanding_parameters: ["COD", "Ammonia"],
      }),
    ).toBe("Cannot issue an ordinary CoA: required results are missing: COD, Ammonia.");
  });
});